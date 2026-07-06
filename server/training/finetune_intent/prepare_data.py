"""JSONL -> instruction-tuning format conversion for intent fine-tuning.

Converts the raw intent classification dataset (JSONL with text/intent/source
fields) into instruction-tuning format (instruction/input/output) suitable for
LoRA fine-tuning of Qwen2.5-1.5B.

The prompt template and intent routing table mirror
``app.domain.agents.chat_intent_classifier`` so the fine-tuned model is trained
on the exact same prompt format used at inference time by
``ChatIntentClassifier``.

Dataset location: ``server/tests/eval/intent/dataset/``
  - train.jsonl  (600 samples)
  - val.jsonl    (100 samples)
  - test.jsonl   (200 samples)

Raw format (one JSON object per line)::

    {"text": "用户消息", "intent": "advice_seeking", "source": "template"}

Output format (instruction-tuning JSONL, one JSON object per line)::

    {
      "instruction": "请分析以下用户消息的意图，返回JSON格式。",
      "input": "今天工作压力好大，感觉撑不住了",
      "output": "{\\"intent_category\\": \\"emotional_vent\\", \\"confidence\\": 0.9, ...}"
    }
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# ── Intent routing table ───────────────────────────────────────────
# Mirrors app.domain.agents.chat_intent_classifier._INTENT_ROUTING
# (need_retrieval / need_tools / need_entity_query per intent).
# Kept as a local copy so prepare_data runs without importing the app
# package (the training environment may not have all app deps installed).

INTENT_ROUTING: dict[str, dict[str, Any]] = {
    "casual_chat": {
        "need_retrieval": False,
        "need_tools": [],
        "need_entity_query": False,
    },
    "emotional_vent": {
        "need_retrieval": False,
        "need_tools": ["analyze_sentiment"],
        "need_entity_query": False,
    },
    "retrospective_query": {
        "need_retrieval": True,
        "need_tools": ["search_diary"],
        "need_entity_query": False,
    },
    "advice_seeking": {
        "need_retrieval": True,
        "need_tools": ["search_diary", "analyze_sentiment"],
        "need_entity_query": False,
    },
    "crisis_signal": {
        "need_retrieval": False,
        "need_tools": [],
        "need_entity_query": False,
    },
    "entity_query": {
        "need_retrieval": False,
        "need_tools": ["query_entity_graph"],
        "need_entity_query": True,
    },
}

#: Canonical intent categories (6 classes).
INTENT_CATEGORIES: list[str] = list(INTENT_ROUTING.keys())

#: Confidence assigned to labeled training examples.
LABELED_CONFIDENCE: float = 0.9

#: Short instruction stored in the JSONL ``instruction`` field.
INSTRUCTION: str = "请分析以下用户消息的意图，返回JSON格式。"

#: Full prompt template — mirrors ``_CHAT_INTENT_PROMPT`` in
#: ``app.domain.agents.chat_intent_classifier``.  ``{content}`` is the
#: format placeholder for the user message; ``{{`` / ``}}`` produce literal
#: braces after ``str.format``.
PROMPT_TEMPLATE: str = """请分析以下用户消息的意图，返回JSON格式。

用户消息：{content}

意图类别（选择最匹配的一个）：
- casual_chat: 闲聊、问候、简短回应
- emotional_vent: 情绪宣泄、表达负面情绪
- retrospective_query: 回溯过去的事情、询问之前的记录
- advice_seeking: 寻求建议、询问方法或解决方案
- crisis_signal: 表达自伤/自杀意念或极度绝望
- entity_query: 询问特定人物或事物的近况

返回JSON：
```json
{{
  "intent_category": "casual_chat",
  "confidence": 0.9,
  "need_retrieval": false,
  "need_tools": [],
  "need_entity_query": false
}}
```"""


def build_output(intent: str, confidence: float = LABELED_CONFIDENCE) -> str:
    """Build the JSON output string for a given intent.

    The output includes the full routing info (need_retrieval, need_tools,
    need_entity_query) derived from :data:`INTENT_ROUTING`, matching the
    format shown in ``_CHAT_INTENT_PROMPT``.

    Args:
        intent: One of the 6 canonical intent categories.
        confidence: Confidence score for the labeled example.

    Returns:
        Compact JSON string, e.g.
        ``{"intent_category": "emotional_vent", "confidence": 0.9, ...}``
    """
    routing = INTENT_ROUTING.get(intent, INTENT_ROUTING["casual_chat"])
    obj: dict[str, Any] = {
        "intent_category": intent,
        "confidence": confidence,
        "need_retrieval": routing["need_retrieval"],
        "need_tools": routing["need_tools"],
        "need_entity_query": routing["need_entity_query"],
    }
    return json.dumps(obj, ensure_ascii=False)


def format_prompt(user_message: str) -> str:
    """Format the full prompt text for a user message.

    This produces the exact same text that ``ChatIntentClassifier`` sends
    to the LLM at inference time (``_CHAT_INTENT_PROMPT.format(content=...)``),
    ensuring training-inference alignment.
    """
    return PROMPT_TEMPLATE.format(content=user_message)


def convert_record(raw: dict[str, Any]) -> dict[str, str]:
    """Convert a single raw dataset record to instruction-tuning format.

    Args:
        raw: ``{"text": ..., "intent": ..., "source": ...}``

    Returns:
        ``{"instruction": ..., "input": ..., "output": ...}``
    """
    text = raw["text"]
    intent = raw["intent"]
    return {
        "instruction": INSTRUCTION,
        "input": text,
        "output": build_output(intent),
    }


def convert_jsonl(input_path: str | Path, output_path: str | Path) -> int:
    """Convert a raw JSONL file to instruction-tuning JSONL.

    Args:
        input_path: Path to the raw JSONL (text/intent/source per line).
        output_path: Path to write the converted JSONL.

    Returns:
        Number of records converted.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with input_path.open("r", encoding="utf-8") as fin, \
         output_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            record = convert_record(raw)
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def load_jsonl(path: str | Path) -> list[dict[str, str]]:
    """Load an instruction-tuning JSONL file into a list of dicts."""
    path = Path(path)
    records: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def prepare_all(
    data_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, str]:
    """Convert train/val/test JSONL from *data_dir* to *output_dir*.

    Args:
        data_dir: Directory containing train.jsonl / val.jsonl / test.jsonl.
        output_dir: Directory to write converted files.

    Returns:
        Mapping of split name -> output file path.
    """
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}
    for split in ("train", "val", "test"):
        src = data_dir / f"{split}.jsonl"
        if not src.is_file():
            print(f"[prepare_data] WARNING: {src} not found, skipping {split}")
            continue
        dst = output_dir / f"{split}.jsonl"
        n = convert_jsonl(src, dst)
        print(f"[prepare_data] {split}: {n} records -> {dst}")
        paths[split] = str(dst)
    return paths


def main() -> None:
    """CLI entry point for standalone data preparation."""
    parser = argparse.ArgumentParser(
        description="Convert intent JSONL to instruction-tuning format.",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="tests/eval/intent/dataset",
        help="Directory containing train/val/test.jsonl (raw format).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="training/finetune_intent/data",
        help="Directory to write converted instruction-tuning JSONL.",
    )
    args = parser.parse_args()
    prepare_all(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
