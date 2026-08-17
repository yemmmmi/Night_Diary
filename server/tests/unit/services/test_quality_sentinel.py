"""Unit tests for the online quality sentinel (robustness P1-4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.infrastructure.models.analysis import AnalysisRow
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.reply_quality import ReplyQualityRow
from app.services.quality_sentinel import (
    get_quality_stats,
    grade_reply,
    run_quality_scan,
)
from app.shared.llm_factory import StubLLMClient

_GOOD_JSON = json.dumps(
    {"safety": 5, "faithfulness": 4, "relevance": 4, "warmth": 5, "rationale": "ok"},
    ensure_ascii=False,
)


def test_grade_reply_parses_scores_and_overall():
    llm = StubLLMClient(reply=_GOOD_JSON)
    result = grade_reply(llm, "今天很累", "辛苦了，抱抱你。")
    assert result is not None
    assert result["scores"]["safety"] == 5
    assert result["scores"]["warmth"] == 5
    assert 1.0 <= result["overall"] <= 5.0


def test_grade_reply_garbage_returns_none():
    llm = StubLLMClient(reply="这不是 JSON")
    assert grade_reply(llm, "今天很累", "辛苦了") is None


def test_grade_reply_empty_reply_returns_none():
    llm = StubLLMClient(reply=_GOOD_JSON)
    assert grade_reply(llm, "输入", "") is None


def test_grade_reply_llm_error_returns_none():
    class _Boom:
        def invoke(self, prompt):  # type: ignore[no-untyped-def]
            raise RuntimeError("LLM down")

    assert grade_reply(_Boom(), "输入", "回复") is None  # type: ignore[arg-type]


def _make_container() -> MagicMock:
    container = MagicMock()
    container._llm_for_tier = MagicMock(return_value=StubLLMClient(reply=_GOOD_JSON))
    return container


def _seed_diary_reply(db_session, *, content: str = "今天很累", reply: str = "辛苦了"):
    entry = DiaryEntryRow(user_id="user-1", content=content, reply=reply)
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    analysis = AnalysisRow(
        diary_id=entry.id,
        created_at=datetime.now(UTC),
        token_cost=10,
        agent_mode="treehole",
        execution_tier="treehole",
        activated_agents="",
    )
    db_session.add(analysis)
    db_session.commit()
    return entry.id


def test_run_quality_scan_persists_scores(db_session):
    _seed_diary_reply(db_session)

    result = run_quality_scan(
        db_session, _make_container(), scenarios=["diary_reply"], limit=5
    )

    assert result["scanned"] >= 1
    rows = db_session.query(ReplyQualityRow).all()
    assert len(rows) == result["scanned"]
    assert rows[0].scenario == "diary_reply"
    assert rows[0].overall is not None
    assert "safety" in (rows[0].scores_json or "")


def test_run_quality_scan_skips_without_llm(db_session):
    container = MagicMock()
    container._llm_for_tier = MagicMock(return_value=None)
    result = run_quality_scan(db_session, container, scenarios=["diary_reply"], limit=5)
    assert result["scanned"] == 0
    assert result["skipped_reason"] == "no_llm"
    assert db_session.query(ReplyQualityRow).count() == 0


def test_get_quality_stats_aggregates(db_session):
    _seed_diary_reply(db_session)
    run_quality_scan(db_session, _make_container(), scenarios=["diary_reply"], limit=5)

    stats = get_quality_stats(db_session, scenario="diary_reply", hours=24 * 30)
    assert stats["total_samples"] >= 1
    diary = stats["by_scenario"]["diary_reply"]
    assert diary["count"] >= 1
    assert 1.0 <= diary["mean"] <= 5.0
    assert diary["p50"] > 0
    assert diary["p95"] >= diary["p50"] or diary["count"] == 1


def test_get_quality_stats_filters_window(db_session):
    _seed_diary_reply(db_session)
    run_quality_scan(db_session, _make_container(), scenarios=["diary_reply"], limit=5)

    # 窗口 0 小时 → 无样本（created_at 是现在，超出 0 小时窗口）
    stats = get_quality_stats(db_session, scenario="diary_reply", hours=0)
    assert stats["total_samples"] == 0
