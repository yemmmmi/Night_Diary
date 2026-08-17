"""Tree-hole digest-quality eval (robustness P0-2).

Runs each fixed diary through the scene-1 tree-hole pipeline
(:func:`run_treehole`) and grades the short reply + structured digest with
the LLM-as-Judge over four dimensions:

- ``summary_faithfulness`` — 摘要忠实概括关键信息，不编造不遗漏
- ``emotion_accuracy`` — 情绪 / 意图与日记一致
- ``temporal_correctness`` — temporal_refs 正确捕获非当天事件（方向/内容），当天事件不误入
- ``reply_brevity`` — 回复 ≤ 40 字且自然

Thresholds are asserted only in **real mode** (CI's stub run never fails on
stubbed scores): mean summary_faithfulness ≥ 3.5 and mean
temporal_correctness ≥ 3.0. Structural invariants (reply length, digest
fields, temporal_refs presence for cross-day cases, crisis short-circuit)
are asserted in **both** modes.

Run ``EVAL_UPDATE_BASELINE=1 make eval`` to (re)write ``BASELINE.md``.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.services.ai.treehole import MAX_REPLY_CHARS, detect_crisis, run_treehole
from tests.eval.judge import LLMJudge
from tests.eval.rubric import EvalRubric, RubricDimension

pytestmark = pytest.mark.eval

SUMMARY_THRESHOLD = 3.5
TEMPORAL_THRESHOLD = 3.0
BASELINE_PATH = Path(__file__).parent / "BASELINE.md"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _treehole_rubric() -> EvalRubric:
    return EvalRubric(
        [
            RubricDimension(
                key="summary_faithfulness",
                name="摘要忠实度",
                description="结构化摘要（summary/topics/key_events）是否忠实概括日记的关键信息，不编造日记中不存在的内容，也不遗漏重要事实。",
                anchors={
                    1: "大量编造或严重遗漏关键事实",
                    2: "多处与日记不符或遗漏重要内容",
                    3: "基本忠实，个别细节不准",
                    4: "忠实概括主要事实，细节恰当",
                    5: "完全忠实，关键事件/话题/情绪层次都准确捕捉",
                },
                positive_example="日记写了加班、项目延期和领导的批评，摘要准确点出这三个事实并归纳出'工作压力大'。",
                negative_example="日记完全没提生病，摘要却说'身体不适需要休息'。",
                weight=1.2,
            ),
            RubricDimension(
                key="emotion_accuracy",
                name="情绪意图准确度",
                description="提取的情绪标签、意图与情绪评分是否与日记表达一致。",
                anchors={
                    1: "情绪判断与日记完全相反",
                    2: "明显错位（如把积极当消极）",
                    3: "基本正确但不够细腻",
                    4: "准确识别主导情绪",
                    5: "准确捕捉情绪层次与变化",
                },
                positive_example="日记通篇焦虑，提取情绪为'焦虑'，意图为'需要情感支持'。",
                negative_example="日记写的是崩溃绝望，却标为'平静'。",
                weight=1.0,
            ),
            RubricDimension(
                key="temporal_correctness",
                name="跨日引用正确性",
                description="temporal_refs 是否准确识别'非当天'发生的事（过去回忆 direction=past / 未来计划 direction=future），且不把当天发生的事误放入 temporal_refs。",
                anchors={
                    1: "完全未识别明显的跨日引用，或把当天事件误当跨日",
                    2: "多数跨日引用漏掉或方向错误",
                    3: "识别了主要跨日引用，个别细节/方向有误",
                    4: "准确识别跨日引用且方向正确",
                    5: "精准识别全部跨日引用，方向/日期提示准确，当天事件零误入",
                },
                positive_example="日记写'昨天和妈妈吵架、下周答辩'，temporal_refs 含 past(昨天/妈妈吵架) 与 future(下周/答辩)。",
                negative_example="日记写'昨天加班'，temporal_refs 为空或把'今天加班'标为过去。",
                weight=1.1,
            ),
            RubricDimension(
                key="reply_brevity",
                name="回复简短自然度",
                description="树洞回复是否 1-3 句、≤40 字，温暖口语化、不分析不说教。",
                anchors={
                    1: "长篇大论或机械模板",
                    2: "超过 40 字或明显套话",
                    3: "简短但略生硬",
                    4: "简短自然，像朋友的回应",
                    5: "极简温暖，一句到两句恰到好处",
                },
                positive_example="今天辛苦了，抱抱你。",
                negative_example="根据你的描述，我建议你从以下几个方面改善你的情绪管理策略……",
                weight=0.8,
            ),
        ]
    )


def _digest_payload(reply: str, digest: Any) -> str:
    """Serialize reply + digest for the judge (JSON, compact)."""
    data = digest.model_dump(mode="json")
    return json.dumps(
        {"reply": reply, "digest": data}, ensure_ascii=False, indent=1
    )


async def _run_case(
    case: dict[str, Any],
    treehole_llm: Any,
    day: date,
) -> Any:
    from app.services.ai.treehole import classify_intent

    intent_result = await classify_intent(case["diary"])
    return await run_treehole(
        content=case["diary"],
        day=day,
        llm=treehole_llm,
        intent_result=intent_result,
        diary_tags=[],
    )


async def test_treehole_extraction_quality(
    treehole_llm: Any,
    judge_llm: Any,
    treehole_cases: list[dict[str, Any]],
    treehole_day: date,
    real_mode: bool,
    model_name: str,
) -> None:
    rubric = _treehole_rubric()
    judge = LLMJudge(judge_llm, rubric, mode="strict")

    summary_scores: list[float] = []
    temporal_scores: list[float] = []
    overalls: list[float] = []
    total_tokens = 0
    rows: list[str] = []
    crisis_cases = 0

    for case in treehole_cases:
        # ── Crisis case: structural short-circuit, never judge the digest ──
        if case.get("expect_crisis"):
            crisis_cases += 1
            assert detect_crisis(case["diary"]) is True, f"{case['id']} 应触发危机短路"
            continue

        outcome = await _run_case(case, treehole_llm, treehole_day)

        # ── Structural invariants (both modes) ──
        assert len(outcome.reply) <= MAX_REPLY_CHARS + 1, f"{case['id']} 回复过长: {outcome.reply}"
        assert outcome.digest.date == treehole_day
        assert outcome.digest.diary.summary, f"{case['id']} 缺摘要"
        expect_complex = case.get("expect_digest_type") == "complex"
        if expect_complex:
            assert outcome.digest.digest_type == "complex", f"{case['id']} 应为 complex"
        if case.get("expect_temporal_refs"):
            assert outcome.digest.diary.temporal_refs, (
                f"{case['id']} 应提取 temporal_refs（跨日引用）"
            )

        # ── Judge the extraction ──
        graded = judge.score(
            case["diary"], _digest_payload(outcome.reply, outcome.digest)
        )
        summary_scores.append(graded.scores.get("summary_faithfulness", 0.0))
        temporal_scores.append(graded.scores.get("temporal_correctness", 0.0))
        overalls.append(graded.overall)
        total_tokens += graded.tokens_in + graded.tokens_out
        rows.append(
            f"| {case['id']} | {graded.scores.get('summary_faithfulness', 0):.1f} | "
            f"{graded.scores.get('temporal_correctness', 0):.1f} | "
            f"{graded.scores.get('emotion_accuracy', 0):.1f} | "
            f"{graded.scores.get('reply_brevity', 0):.1f} | {graded.overall:.2f} |"
        )

    mean_summary = _mean(summary_scores)
    mean_temporal = _mean(temporal_scores)
    mean_overall = _mean(overalls)
    print(
        f"\n[EVAL SUMMARY] suite=treehole mode={'real' if real_mode else 'stub'} "
        f"cases={len(treehole_cases) - crisis_cases} mean_summary_faithfulness="
        f"{mean_summary:.2f} mean_temporal_correctness={mean_temporal:.2f} "
        f"mean_overall={mean_overall:.2f} total_tokens={total_tokens}"
    )

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        body = (
            f"## TreeHole digest ({model_name}, {len(treehole_cases) - crisis_cases} cases)\n\n"
            f"- mean summary_faithfulness: **{mean_summary:.2f}** / 5\n"
            f"- mean temporal_correctness: **{mean_temporal:.2f}** / 5\n"
            f"- mean overall: **{mean_overall:.2f}** / 5\n\n"
            "| case | faithfulness | temporal | emotion | brevity | overall |\n"
            "|---|---|---|---|---|---|\n"
            + "\n".join(rows)
        )
        _update_baseline_section("treehole", body)

    if real_mode:
        assert mean_summary >= SUMMARY_THRESHOLD, (
            f"mean summary_faithfulness {mean_summary:.2f} < {SUMMARY_THRESHOLD}"
        )
        assert mean_temporal >= TEMPORAL_THRESHOLD, (
            f"mean temporal_correctness {mean_temporal:.2f} < {TEMPORAL_THRESHOLD}"
        )
    else:
        assert all(1.0 <= s <= 5.0 for s in summary_scores)


def _update_baseline_section(marker: str, body: str) -> None:
    """Replace (or append) a ``<!-- marker -->``-delimited section in BASELINE.md."""
    begin = f"<!-- BEGIN:{marker} -->"
    end = f"<!-- END:{marker} -->"
    block = f"{begin}\n{body}\n{end}"

    existing = (
        BASELINE_PATH.read_text(encoding="utf-8")
        if BASELINE_PATH.exists()
        else (
            "# Tree-Hole Digest Quality Baseline\n\n"
            "由 `EVAL_UPDATE_BASELINE=1 make eval` 生成。后续改动树洞 prompt 后对照此文件做回归。\n\n"
        )
    )
    if begin in existing and end in existing:
        head = existing.split(begin)[0]
        tail = existing.split(end)[1]
        updated = f"{head}{block}{tail}"
    else:
        updated = f"{existing}\n{block}\n"
    BASELINE_PATH.write_text(updated, encoding="utf-8")
