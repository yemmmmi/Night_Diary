"""微调 bge-reranker-base 交叉编码器（LoRA 或全量）。

bge-reranker-base 是小模型（~560M），8GB 显存可全量微调；
若无 GPU 或想更快，可用 LoRA 模式（CPU 也能跑，但慢）。

用法：
    # 全量微调（推荐，模型小）
    python -m scripts.finetune.train_reranker_lora --train data.train.jsonl --val data.val.jsonl --out ./models/reranker-night-diary

    # LoRA 微调（省显存，适合更低配）
    python -m scripts.finetune.train_reranker_lora --train data.train.jsonl --val data.val.jsonl --out ./models/reranker-night-diary --lora --lora-r 8

依赖：
    pip install sentence-transformers torch datasets
    # 如需 LoRA:
    pip install peft
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# 禁用 tensorboard/tensorflow 集成，避免 anaconda base 环境中 tensorflow 残留导致的冲突
os.environ.setdefault("TRANSFORMERS_NO_TENSORBOARD", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TENSORBOARD_PROXY_URL", "")
# 阻止 transformers.Trainer 尝试导入 tensorboard
import types

_tb_stub = types.ModuleType("torch.utils.tensorboard")
_tb_stub.SummaryWriter = None
sys.modules.setdefault("torch.utils.tensorboard", _tb_stub)

logger = logging.getLogger("train_reranker_lora")


def load_jsonl(path: str) -> list[dict]:
    """加载 JSONL 格式训练数据。每行：{"query":..., "passage":..., "label":0/1}"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    logger.info("加载 %s: %d 条", path, len(rows))
    return rows


def train_full(
    train_path: str,
    val_path: str,
    out_dir: str,
    *,
    base_model: str = "BAAI/bge-reranker-base",
    epochs: int = 3,
    batch_size: int = 16,
    lr: float = 2e-5,
    warmup_ratio: float = 0.1,
) -> None:
    """全量微调 bge-reranker-base。

    模型仅 ~560M 参数，8GB 显存 batch_size=16 无压力。
    """
    from sentence_transformers import CrossEncoder, InputExample
    from sentence_transformers.cross_encoder.evaluation import CECorrelationEvaluator
    from torch.utils.data import DataLoader

    train_rows = load_jsonl(train_path)
    val_rows = load_jsonl(val_path)

    # 转为 InputExample 格式
    train_samples = [
        InputExample(texts=[r["query"], r["passage"]], label=float(r["label"]))
        for r in train_rows
    ]
    val_samples = [
        InputExample(texts=[r["query"], r["passage"]], label=float(r["label"]))
        for r in val_rows
    ]

    logger.info("初始化基座模型: %s", base_model)
    model = CrossEncoder(base_model, num_labels=1, max_length=512)

    # 评估器
    evaluator = CECorrelationEvaluator.from_input_examples(
        val_samples, name="night-diary-val"
    )

    # DataLoader
    train_dataloader = DataLoader(train_samples, shuffle=True, batch_size=batch_size)

    logger.info("开始训练: epochs=%d batch_size=%d lr=%s", epochs, batch_size, lr)
    model.fit(
        train_dataloader=train_dataloader,
        evaluator=evaluator,
        epochs=epochs,
        warmup_steps=int(len(train_dataloader) * epochs * warmup_ratio),
        optimizer_params={"lr": lr},
        output_path=out_dir,
        show_progress_bar=True,
        save_best_model=False,
    )

    # 手动保存完整模型（sentence-transformers 5.x 的 save_best_model 有时不会写出权重）
    logger.info("保存模型至 %s", out_dir)
    model.save(out_dir)

    logger.info("训练完成，模型已保存至 %s", out_dir)


def train_lora(
    train_path: str,
    val_path: str,
    out_dir: str,
    *,
    base_model: str = "BAAI/bge-reranker-base",
    epochs: int = 3,
    batch_size: int = 16,
    lr: float = 1e-4,
    lora_r: int = 8,
    lora_alpha: int = 16,
) -> None:
    """LoRA 微调 bge-reranker-base。

    显存占用更低，适合 <8GB GPU 或 CPU。
    训练后需合并 LoRA 权重再保存，或用 peft 加载。
    """
    try:
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            Trainer,
            TrainingArguments,
        )
    except ImportError:
        logger.error("LoRA 模式需要额外依赖: pip install peft transformers datasets torch")
        raise

    train_rows = load_jsonl(train_path)
    val_rows = load_jsonl(val_path)

    logger.info("初始化基座模型: %s", base_model)
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    base = AutoModelForSequenceClassification.from_pretrained(
        base_model, num_labels=1, problem_type="regression"
    )

    # 注入 LoRA
    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=0.1,
        target_modules=["query", "key", "value", "dense"],
    )
    model = get_peft_model(base, lora_config)
    model.print_trainable_parameters()

    # 预处理数据
    def tokenize(rows: list[dict]) -> Dataset:
        encodings = tokenizer(
            [r["query"] for r in rows],
            [r["passage"] for r in rows],
            truncation=True,
            max_length=512,
            padding="max_length",
        )
        encodings["labels"] = [float(r["label"]) for r in rows]
        return Dataset.from_dict(encodings)

    train_ds = tokenize(train_rows)
    val_ds = tokenize(val_rows)

    args = TrainingArguments(
        output_dir=out_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=lr,
        warmup_ratio=0.1,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        save_total_limit=2,
        logging_steps=20,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
    )

    logger.info("开始 LoRA 训练: r=%d alpha=%d epochs=%d", lora_r, lora_alpha, epochs)
    trainer.train()

    # 合并 LoRA 权重并保存为完整模型（便于 sentence-transformers 加载）
    logger.info("合并 LoRA 权重并保存至 %s", out_dir)
    merged = model.merge_and_unload()
    merged.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    logger.info("训练完成，合并后的完整模型已保存至 %s", out_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="微调 bge-reranker 交叉编码器")
    parser.add_argument("--train", required=True, help="训练集 JSONL 路径")
    parser.add_argument("--val", required=True, help="验证集 JSONL 路径")
    parser.add_argument("--out", required=True, help="输出模型目录")
    parser.add_argument("--base-model", default="BAAI/bge-reranker-base", help="基座模型")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=None, help="学习率（默认全量2e-5/LoRA 1e-4）")
    parser.add_argument("--lora", action="store_true", help="使用 LoRA 微调（省显存）")
    parser.add_argument("--lora-r", type=int, default=8, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=16, help="LoRA alpha")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.lora:
        train_lora(
            args.train,
            args.val,
            str(out_dir),
            base_model=args.base_model,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr or 1e-4,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
        )
    else:
        train_full(
            args.train,
            args.val,
            str(out_dir),
            base_model=args.base_model,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr or 2e-5,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
