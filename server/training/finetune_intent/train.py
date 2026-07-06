"""LoRA fine-tuning for chat intent classification (Qwen2.5-1.5B).

Reads ``configs/default.yaml``, converts the intent dataset to
instruction-tuning format via :mod:`prepare_data`, then fine-tunes
``Qwen/Qwen2.5-1.5B`` with LoRA using transformers + peft + datasets.

Training flow::

    1. Load YAML config (configs/default.yaml)
    2. Convert raw JSONL -> instruction-tuning JSONL (prepare_data)
    3. Load base model + tokenizer, attach LoRA adapter
    4. Tokenise (mask prompt tokens, loss only on output)
    5. Train with HuggingFace Trainer (predict_with_generate for macro_f1)
    6. Save LoRA adapter to outputs/final/

Usage::

    cd server

    # Default config
    python -m training.finetune_intent.train

    # Override via CLI
    python -m training.finetune_intent.train \\
        --base-model Qwen/Qwen2.5-1.5B \\
        --num-train-epochs 5 \\
        --learning-rate 1e-4 \\
        --batch-size 4

    # Skip data prep (reuse existing converted data)
    python -m training.finetune_intent.train --skip-prepare

CLI arguments override the YAML config values.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import torch
import yaml
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

from training.finetune_intent.prepare_data import (
    INTENT_CATEGORIES,
    format_prompt,
    load_jsonl,
    prepare_all,
)

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────
_MODULE_DIR = Path(__file__).resolve().parent
_DEFAULT_CONFIG = _MODULE_DIR / "configs" / "default.yaml"


# ── Config loading ──────────────────────────────────────────────────

def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load YAML config from *config_path*."""
    with Path(config_path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Tokenisation ────────────────────────────────────────────────────

def build_tokenize_fn(tokenizer: Any, max_seq_length: int):
    """Return a ``map()`` callable that tokenises instruction-tuning records.

    Each record has ``instruction``, ``input``, ``output``.  The full prompt
    text is constructed via :func:`format_prompt` (matching the inference
    prompt).  Labels mask the prompt tokens so loss is only computed on the
    output portion.

    Training text layout::

        [prompt tokens] [output tokens] [EOS]
                          ^^^^^^^^^^^^^^^^^^^^
                          loss computed here (labels != -100)
    """

    def tokenise(example: dict[str, str]) -> dict[str, list[int]]:
        prompt = format_prompt(example["input"])
        output = example["output"]

        # Append EOS so the model learns to stop generation
        output_with_eos = output + tokenizer.eos_token

        prompt_ids: list[int] = tokenizer(
            prompt, add_special_tokens=False
        )["input_ids"]
        output_ids: list[int] = tokenizer(
            output_with_eos, add_special_tokens=False
        )["input_ids"]

        input_ids = prompt_ids + output_ids
        labels = [-100] * len(prompt_ids) + list(output_ids)

        # Truncate to max_seq_length
        if len(input_ids) > max_seq_length:
            input_ids = input_ids[:max_seq_length]
            labels = labels[:max_seq_length]

        return {
            "input_ids": input_ids,
            "labels": labels,
            "attention_mask": [1] * len(input_ids),
        }

    return tokenise


# ── Metrics ─────────────────────────────────────────────────────────

_JSON_OBJ_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def extract_intent(text: str) -> str:
    """Extract ``intent_category`` from generated or label text.

    Handles raw JSON, ``\\`\\`\\`json ... \\`\\`\\``` wrapped, and partial JSON.
    Falls back to ``"casual_chat"`` (the majority class) on parse failure.
    """
    cleaned = text.strip()

    # Strip code fences
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # Try direct parse
    try:
        data = json.loads(cleaned)
        return str(data.get("intent_category", "casual_chat"))
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Try extracting first JSON object via regex
    match = _JSON_OBJ_RE.search(cleaned)
    if match:
        try:
            data = json.loads(match.group(0))
            return str(data.get("intent_category", "casual_chat"))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    return "casual_chat"


def compute_macro_f1(
    predictions: list[str],
    references: list[str],
    classes: list[str] | None = None,
) -> dict[str, float]:
    """Compute macro-averaged F1 and accuracy over intent categories.

    Pure-Python implementation (no sklearn dependency).
    """
    if classes is None:
        classes = INTENT_CATEGORIES

    pred_intents = [extract_intent(p) for p in predictions]
    gold_intents = [extract_intent(r) for r in references]

    # Accuracy
    correct = sum(1 for p, g in zip(pred_intents, gold_intents, strict=False) if p == g)
    accuracy = correct / len(gold_intents) if gold_intents else 0.0

    # Per-class F1
    f1_scores: list[float] = []
    for cls in classes:
        tp = sum(1 for p, g in zip(pred_intents, gold_intents, strict=False) if p == cls and g == cls)
        fp = sum(1 for p, g in zip(pred_intents, gold_intents, strict=False) if p == cls and g != cls)
        fn = sum(1 for p, g in zip(pred_intents, gold_intents, strict=False) if p != cls and g == cls)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
        f1_scores.append(f1)

    macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
    return {"macro_f1": macro_f1, "accuracy": accuracy}


def build_compute_metrics_fn(tokenizer: Any):
    """Build a ``compute_metrics`` closure for the Trainer.

    With ``predict_with_generate=True`` the Trainer generates text on the
    eval set and passes ``EvalPrediction(predictions=<token_ids>,
    label_ids=<token_ids>)``.  We decode both, extract intents, and compute
    macro-F1.
    """

    def compute_metrics(eval_pred) -> dict[str, float]:
        import numpy as np

        predictions, labels = eval_pred
        if isinstance(predictions, tuple):
            predictions = predictions[0]

        # Replace -100 (masked label tokens) with pad token for decoding
        labels_np = np.where(labels != -100, labels, tokenizer.pad_token_id)

        pred_texts = tokenizer.batch_decode(predictions, skip_special_tokens=True)
        gold_texts = tokenizer.batch_decode(labels_np, skip_special_tokens=True)

        return compute_macro_f1(pred_texts, gold_texts)

    return compute_metrics


# ── CLI ─────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LoRA fine-tuning for chat intent classification (Qwen2.5-1.5B).",
    )
    parser.add_argument("--config", type=str, default=str(_DEFAULT_CONFIG),
                        help="Path to YAML config file.")
    parser.add_argument("--base-model", type=str, default=None,
                        help="Override base_model.")
    parser.add_argument("--learning-rate", type=float, default=None,
                        help="Override learning_rate.")
    parser.add_argument("--num-train-epochs", type=int, default=None,
                        help="Override num_train_epochs.")
    parser.add_argument("--batch-size", type=int, default=None,
                        help="Override per_device_train/eval_batch_size.")
    parser.add_argument("--gradient-accumulation-steps", type=int, default=None,
                        help="Override gradient_accumulation_steps.")
    parser.add_argument("--max-seq-length", type=int, default=None,
                        help="Override max_seq_length.")
    parser.add_argument("--lora-r", type=int, default=None,
                        help="Override LoRA r.")
    parser.add_argument("--lora-alpha", type=int, default=None,
                        help="Override LoRA alpha.")
    parser.add_argument("--lora-dropout", type=float, default=None,
                        help="Override LoRA dropout.")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Override output_dir.")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Override dataset directory (containing train/val/test.jsonl).")
    parser.add_argument("--fp16", action="store_true", default=None,
                        help="Force FP16 training (GPU).")
    parser.add_argument("--no-fp16", action="store_true", default=None,
                        help="Disable FP16 (CPU training).")
    parser.add_argument("--seed", type=int, default=None,
                        help="Override random seed.")
    parser.add_argument("--skip-prepare", action="store_true",
                        help="Skip data preparation (reuse existing converted data).")
    return parser.parse_args()


def apply_overrides(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Apply CLI overrides to the config dict (in-place)."""
    if args.base_model:
        cfg["base_model"] = args.base_model
    if args.max_seq_length is not None:
        cfg["max_seq_length"] = args.max_seq_length
    if args.lora_r is not None:
        cfg["lora"]["r"] = args.lora_r
    if args.lora_alpha is not None:
        cfg["lora"]["alpha"] = args.lora_alpha
    if args.lora_dropout is not None:
        cfg["lora"]["dropout"] = args.lora_dropout
    if args.learning_rate is not None:
        cfg["training"]["learning_rate"] = args.learning_rate
    if args.num_train_epochs is not None:
        cfg["training"]["num_train_epochs"] = args.num_train_epochs
    if args.batch_size is not None:
        cfg["training"]["per_device_train_batch_size"] = args.batch_size
        cfg["training"]["per_device_eval_batch_size"] = args.batch_size
    if args.gradient_accumulation_steps is not None:
        cfg["training"]["gradient_accumulation_steps"] = args.gradient_accumulation_steps
    if args.output_dir:
        cfg["output_dir"] = args.output_dir
    if args.data_dir:
        data_dir = Path(args.data_dir)
        cfg["data"]["train_file"] = str(data_dir / "train.jsonl")
        cfg["data"]["val_file"] = str(data_dir / "val.jsonl")
        cfg["data"]["test_file"] = str(data_dir / "test.jsonl")
    if args.no_fp16:
        cfg["fp16"] = False
    elif args.fp16:
        cfg["fp16"] = True
    if args.seed is not None:
        cfg["seed"] = args.seed
    return cfg


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    cfg = apply_overrides(cfg, args)

    # ── Print config summary ──
    print("=" * 60)
    print("LoRA Fine-tuning — Chat Intent Classification")
    print(f"  Base model : {cfg['base_model']}")
    print(f"  LoRA r/a/d : {cfg['lora']['r']}/{cfg['lora']['alpha']}/{cfg['lora']['dropout']}")
    print(f"  Epochs     : {cfg['training']['num_train_epochs']}")
    print(f"  LR         : {cfg['training']['learning_rate']}")
    print(f"  Batch size : {cfg['training']['per_device_train_batch_size']}")
    print(f"  Grad accum : {cfg['training']['gradient_accumulation_steps']}")
    print(f"  Max seq    : {cfg['max_seq_length']}")
    print(f"  FP16       : {cfg['fp16']}")
    print(f"  Output dir : {cfg['output_dir']}")
    print("=" * 60)

    # ── Step 1: Prepare data ──
    print("\n[1/4] Preparing data...")
    prepared_dir = Path(cfg["data"]["prepared_dir"])
    if not args.skip_prepare:
        raw_data_dir = str(Path(cfg["data"]["train_file"]).parent)
        prepare_all(raw_data_dir, prepared_dir)
    else:
        print("  (skipped — using existing converted data)")

    train_jsonl = prepared_dir / "train.jsonl"
    val_jsonl = prepared_dir / "val.jsonl"
    if not train_jsonl.is_file() or not val_jsonl.is_file():
        raise FileNotFoundError(
            f"Prepared data not found: {train_jsonl} / {val_jsonl}. "
            "Run without --skip-prepare first."
        )

    # ── Step 2: Load datasets ──
    print("\n[2/4] Loading datasets...")
    train_records = load_jsonl(train_jsonl)
    val_records = load_jsonl(val_jsonl)
    train_ds = Dataset.from_list(train_records)
    val_ds = Dataset.from_list(val_records)
    print(f"  Train: {len(train_ds)} samples")
    print(f"  Val  : {len(val_ds)} samples")

    # ── Step 3: Load model & tokenizer ──
    print("\n[3/4] Loading model and tokenizer...")
    model_name = cfg["base_model"]
    tokenizer_name = cfg.get("tokenizer_name") or model_name

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.float16 if cfg["fp16"] else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        torch_dtype=dtype,
        device_map="auto",
    )
    model.config.use_cache = False

    # ── LoRA ──
    lora_cfg = LoraConfig(
        r=cfg["lora"]["r"],
        lora_alpha=cfg["lora"]["alpha"],
        lora_dropout=cfg["lora"]["dropout"],
        target_modules=cfg["lora"]["target_modules"],
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    # ── Tokenise ──
    max_seq = cfg["max_seq_length"]
    tokenise_fn = build_tokenize_fn(tokenizer, max_seq)
    train_ds = train_ds.map(tokenise_fn, remove_columns=train_ds.column_names)
    val_ds = val_ds.map(tokenise_fn, remove_columns=val_ds.column_names)

    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        padding=True,
        return_tensors="pt",
    )

    # ── Step 4: Train ──
    print("\n[4/4] Starting training...")

    training_kwargs: dict[str, Any] = {
        "output_dir": cfg["output_dir"],
        "learning_rate": cfg["training"]["learning_rate"],
        "num_train_epochs": cfg["training"]["num_train_epochs"],
        "per_device_train_batch_size": cfg["training"]["per_device_train_batch_size"],
        "per_device_eval_batch_size": cfg["training"]["per_device_eval_batch_size"],
        "gradient_accumulation_steps": cfg["training"]["gradient_accumulation_steps"],
        "warmup_ratio": cfg["training"]["warmup_ratio"],
        "weight_decay": cfg["training"]["weight_decay"],
        "max_grad_norm": cfg["training"]["max_grad_norm"],
        "lr_scheduler_type": cfg["training"]["lr_scheduler_type"],
        "save_strategy": cfg["eval"]["save_strategy"],
        "load_best_model_at_end": cfg["eval"]["load_best_model_at_end"],
        "metric_for_best_model": cfg["eval"]["metric_for_best_model"],
        "greater_is_better": cfg["eval"]["greater_is_better"],
        "predict_with_generate": cfg["eval"]["predict_with_generate"],
        "save_total_limit": cfg["save_total_limit"],
        "logging_steps": cfg["logging_steps"],
        "seed": cfg["seed"],
        "fp16": cfg["fp16"],
        "bf16": cfg["bf16"],
        "report_to": [],
    }

    # eval_strategy was renamed from evaluation_strategy in transformers 4.46+.
    # Try the newer name first, fall back to the legacy name.
    eval_strat = cfg["eval"]["evaluation_strategy"]
    try:
        training_args = TrainingArguments(**training_kwargs, eval_strategy=eval_strat)
    except TypeError:
        training_args = TrainingArguments(
            **training_kwargs, evaluation_strategy=eval_strat
        )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=data_collator,
        compute_metrics=build_compute_metrics_fn(tokenizer),
    )

    trainer.train()

    # ── Save final model ──
    final_dir = Path(cfg["output_dir"]) / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    # ── Print summary ──
    print("\n" + "=" * 60)
    print("Training complete!")
    print(f"  Model saved to: {final_dir}")
    print("\n  To evaluate on the test set:")
    print("    python -m training.finetune_intent.train --skip-prepare \\")
    print(f"      --output-dir {cfg['output_dir']}-eval")
    print("\n  To use in inference:")
    print("    from training.finetune_intent.inference import FinetunedIntentLLM")
    print(f"    llm = FinetunedIntentLLM(model_path='{final_dir}')")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
