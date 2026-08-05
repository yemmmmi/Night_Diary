"""离线评估 reranker：对比基座 vs 微调模型在验证集上的指标。

指标：
- Accuracy / Precision / Recall / F1（按 0.5 阈值二分类）
- AUC（连续分值排序质量）

用法：
    python -m scripts.finetune.eval_reranker --val data.val.jsonl --base BAAI/bge-reranker-base --finetuned ./models/reranker-night-diary
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("eval_reranker")


def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def compute_auc(scores: list[float], labels: list[int]) -> float:
    """简易 AUC 计算（Mann-Whitney U 统计量）。"""
    pos_scores = [s for s, l in zip(scores, labels) if l == 1]
    neg_scores = [s for s, l in zip(scores, labels) if l == 0]
    if not pos_scores or not neg_scores:
        return 0.0

    correct = 0
    ties = 0
    for ps in pos_scores:
        for ns in neg_scores:
            if ps > ns:
                correct += 1
            elif ps == ns:
                ties += 0.5
    return (correct + ties) / (len(pos_scores) * len(neg_scores))


def evaluate_model(model_path: str, val_rows: list[dict]) -> dict:
    """评估单个模型，返回指标字典。"""
    from sentence_transformers import CrossEncoder

    logger.info("加载模型: %s", model_path)
    model = CrossEncoder(model_path, num_labels=1, max_length=512)

    pairs = [(r["query"], r["passage"]) for r in val_rows]
    labels = [int(r["label"]) for r in val_rows]

    logger.info("推理 %d 对...", len(pairs))
    raw_scores = model.predict(pairs)
    scores = [float(s) for s in raw_scores]

    preds = [1 if s > 0.5 else 0 for s in scores]
    tp = sum(1 for p, l in zip(preds, labels) if p == 1 and l == 1)
    fp = sum(1 for p, l in zip(preds, labels) if p == 1 and l == 0)
    tn = sum(1 for p, l in zip(preds, labels) if p == 0 and l == 0)
    fn = sum(1 for p, l in zip(preds, labels) if p == 0 and l == 1)

    accuracy = (tp + tn) / len(labels) if labels else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    auc = compute_auc(scores, labels)

    return {
        "model": model_path,
        "samples": len(labels),
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "auc": round(auc, 4),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def print_comparison(base_metrics: dict, ft_metrics: dict) -> None:
    """打印对比表。"""
    print("\n" + "=" * 60)
    print(f"{'指标':<15} {'基座模型':>15} {'微调模型':>15} {'变化':>12}")
    print("-" * 60)

    for key in ["accuracy", "precision", "recall", "f1", "auc"]:
        base_val = base_metrics[key]
        ft_val = ft_metrics[key]
        delta = ft_val - base_val
        arrow = "+" if delta > 0.001 else ("-" if delta < -0.001 else "=")
        print(f"{key:<15} {base_val:>15.4f} {ft_val:>15.4f} {arrow}{abs(delta):>8.4f}")

    print("=" * 60)
    print(f"\n基座: {base_metrics['model']}")
    print(f"微调: {ft_metrics['model']}")
    print(f"样本: {base_metrics['samples']} 条\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="评估 reranker 微调效果")
    parser.add_argument("--val", required=True, help="验证集 JSONL 路径")
    parser.add_argument("--base", default="BAAI/bge-reranker-base", help="基座模型路径")
    parser.add_argument("--finetuned", required=True, help="微调后模型路径")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    val_rows = load_jsonl(args.val)
    if not val_rows:
        logger.error("验证集为空")
        return 1

    logger.info("验证集 %d 条", len(val_rows))

    base_metrics = evaluate_model(args.base, val_rows)
    ft_metrics = evaluate_model(args.finetuned, val_rows)

    print_comparison(base_metrics, ft_metrics)

    result_path = Path(args.finetuned) / "eval_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({"base": base_metrics, "finetuned": ft_metrics}, f, ensure_ascii=False, indent=2)
    logger.info("评估结果已保存至 %s", result_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
