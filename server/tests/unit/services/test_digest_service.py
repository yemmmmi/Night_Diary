"""Unit tests for the daily digest model + service (V3 tree-hole Task 1)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.infrastructure.models.memory_card import MemoryCardRow
from app.services.digest_service import (
    cards_to_digest,
    format_day_digest,
    get_digest,
    refresh_cards_section,
    upsert_digest,
)
from app.shared.digest import (
    CardDigest,
    DiaryDigest,
    DiaryDigestPart,
    DigestEntity,
    TemporalRef,
)


def _card(
    *,
    emotion: str = "焦虑",
    summary: str = "加班到很晚",
    tags: list[str] | None = None,
    mood: float = 0.3,
    created_at: datetime | None = None,
) -> MemoryCardRow:
    row = MemoryCardRow(
        card_id="c" + str(abs(hash((emotion, summary)))),
        user_id="user-1",
        emotion=emotion,
        emotions_json='["焦虑", "疲惫"]',
        event_summary=summary,
        mood_score=mood,
        tags_json='["加班"]' if tags is None else __import__("json").dumps(tags),
    )
    row.created_at = created_at or datetime(2026, 8, 12, 10, 0)
    return row


# ── Schema ──────────────────────────────────────────────────────────────


def test_basic_digest_schema_roundtrip():
    """basic digest serializes/deserializes losslessly."""
    d = DiaryDigest(
        digest_type="basic",
        date=date(2026, 8, 12),
        source="card",
        cards=[CardDigest(emotion="焦虑", emotions=["焦虑"], mood=0.3, tags=["加班"])],
        diary=DiaryDigestPart(
            intent="pure_record",
            intent_confidence=0.95,
            emotion="中性",
            topics=["加班"],
            summary="加班到很晚。",
        ),
    )
    restored = DiaryDigest.model_validate_json(d.model_dump_json())
    assert restored.digest_type == "basic"
    assert restored.date == date(2026, 8, 12)
    assert restored.cards[0].emotion == "焦虑"
    assert restored.diary.intent == "pure_record"


def test_complex_digest_with_temporal_refs_schema():
    """complex 模版含全部扩展字段（key_events/relationships/temporal_refs）。"""
    d = DiaryDigest(
        digest_type="complex",
        date=date(2026, 8, 12),
        source="llm",
        diary=DiaryDigestPart(
            intent="emotional_support",
            emotion="焦虑",
            emotion_score=-0.6,
            mood=0.2,
            topics=["项目", "家庭"],
            entities=[DigestEntity(name="李总", relation="领导", sentiment=-0.6)],
            summary="项目受阻。",
            temporal_refs=[
                TemporalRef(direction="past", date_hint="昨天", summary="和妈妈吵架"),
                TemporalRef(direction="future", date_hint="下周五", summary="项目答辩"),
            ],
            key_events=["和领导争执", "得知项目延期"],
            emotional_shifts=["平静", "焦虑", "低落"],
            relationships=[DigestEntity(name="李总", relation="领导", sentiment=-0.6)],
            conflicts=["想推进项目但被否决"],
            concerns=["担心延期影响晋升"],
        ),
    )
    restored = DiaryDigest.model_validate_json(d.model_dump_json())
    assert restored.digest_type == "complex"
    assert len(restored.diary.temporal_refs) == 2
    assert restored.diary.temporal_refs[0].direction == "past"
    assert restored.diary.temporal_refs[1].date_hint == "下周五"
    assert restored.diary.key_events[0] == "和领导争执"
    assert restored.diary.conflicts == ["想推进项目但被否决"]


def test_schema_tolerates_missing_complex_fields():
    """basic 模版缺 complex 字段时反序列化不失败（容错）。"""
    raw = (
        '{"v":1,"digest_type":"basic","date":"2026-08-12","source":"llm",'
        '"diary":{"intent":"pure_record","summary":"记了流水账"}}'
    )
    d = DiaryDigest.model_validate_json(raw)
    assert d.diary.summary == "记了流水账"
    assert d.diary.key_events == []  # complex-only 字段默认空


# ── Card mapping ────────────────────────────────────────────────────────


def test_cards_to_digest_maps_structured_fields():
    """卡片字段直接映射，零 LLM。"""
    cards = [_card(), _card(emotion="疲惫", summary="和朋友吃了火锅", tags=["朋友", "美食"])]
    digest_cards = cards_to_digest(cards)
    assert len(digest_cards) == 2
    first = digest_cards[0]
    assert first.emotion == "焦虑"
    assert first.emotions == ["焦虑", "疲惫"]
    assert first.mood == 0.3
    assert first.tags == ["加班"]
    assert first.summary == "加班到很晚"


# ── Service ─────────────────────────────────────────────────────────────


def test_upsert_get_roundtrip(db_session: Session):
    """upsert 后可读回同一 digest。"""
    d = DiaryDigest(digest_type="basic", date=date(2026, 8, 12), source="card")
    upsert_digest(db_session, user_id="user-1", day=date(2026, 8, 12), digest=d)
    db_session.commit()

    got = get_digest(db_session, user_id="user-1", day=date(2026, 8, 12))
    assert got is not None
    assert got.date == date(2026, 8, 12)

    # 再次 upsert（更新路径）不炸唯一约束
    d2 = DiaryDigest(digest_type="complex", date=date(2026, 8, 12), source="llm")
    upsert_digest(db_session, user_id="user-1", day=date(2026, 8, 12), digest=d2)
    db_session.commit()
    got2 = get_digest(db_session, user_id="user-1", day=date(2026, 8, 12))
    assert got2 is not None and got2.digest_type == "complex"


def test_get_digest_returns_none_for_missing_day(db_session: Session):
    """无 digest 的日子返回 None（场景二回落全文渲染）。"""
    assert get_digest(db_session, user_id="user-1", day=date(2026, 8, 13)) is None


def test_refresh_cards_section_creates_basic_card_digest(db_session: Session):
    """卡片日：refresh 创建 basic 卡片 digest（source=card），零 LLM。"""
    db_session.add(_card())
    db_session.commit()

    digest = refresh_cards_section(db_session, user_id="user-1", day=date(2026, 8, 12))
    db_session.commit()

    assert digest.digest_type == "basic"
    assert digest.source == "card"
    assert len(digest.cards) == 1
    assert digest.diary.intent == ""  # 无 diary 段


def test_refresh_cards_section_keeps_diary_section(db_session: Session):
    """混合日：refresh 只改 cards 段，diary 段（LLM 产物）不动，source 升级。"""
    db_session.add(_card())
    db_session.commit()

    # 先有带 diary 段的 digest
    digest = DiaryDigest(
        digest_type="complex",
        date=date(2026, 8, 12),
        source="llm",
        diary=DiaryDigestPart(
            intent="emotional_support",
            emotion="焦虑",
            summary="项目受阻、与领导关系紧张。",
            key_events=["和领导争执"],
            temporal_refs=[TemporalRef(direction="past", date_hint="昨天", summary="吵架")],
        ),
    )
    upsert_digest(db_session, user_id="user-1", day=date(2026, 8, 12), digest=digest)
    db_session.commit()

    # 卡片变化 → 只重建 cards 段
    refreshed = refresh_cards_section(db_session, user_id="user-1", day=date(2026, 8, 12))
    db_session.commit()

    assert refreshed.source == "card+llm"
    assert len(refreshed.cards) == 1
    assert refreshed.diary.intent == "emotional_support"  # diary 段未动
    assert refreshed.diary.key_events == ["和领导争执"]
    assert refreshed.diary.temporal_refs[0].summary == "吵架"
    assert refreshed.digest_type == "complex"


def test_refresh_cards_section_empty_day_creates_empty_basic(db_session: Session):
    """无卡无日记的空日：refresh 建一个空 basic digest（幂等可用）。"""
    digest = refresh_cards_section(db_session, user_id="user-1", day=date(2026, 8, 12))
    db_session.commit()
    assert digest.digest_type == "basic"
    assert digest.cards == []


# ── Formatting (scene-2 consumption) ────────────────────────────────────


def test_format_day_digest_returns_empty_when_missing(db_session: Session):
    """无 digest → 空串（调用方回落全文渲染）。"""
    assert format_day_digest(db_session, user_id="user-1", day=date(2026, 8, 12)) == ""


def test_format_day_digest_basic_renders_compact_block(db_session: Session):
    """basic digest 渲染为紧凑一行块。"""
    digest = DiaryDigest(
        digest_type="basic",
        date=date(2026, 8, 12),
        source="card+llm",
        cards=[CardDigest(emotion="焦虑", emotions=["焦虑"], mood=0.3, tags=["加班"], summary="加班到很晚")],
        diary=DiaryDigestPart(
            intent="pure_record", emotion="中性", topics=["加班"], summary="加班到很晚，有点累。"
        ),
    )
    upsert_digest(db_session, user_id="user-1", day=date(2026, 8, 12), digest=digest)
    db_session.commit()

    text = format_day_digest(db_session, user_id="user-1", day=date(2026, 8, 12))
    assert "2026-08-12" in text
    assert "卡片焦虑" in text
    assert "加班到很晚" in text
    assert "话题：加班" in text
    assert "情绪：中性" in text


def test_format_day_digest_complex_includes_rich_fields(db_session: Session):
    """complex digest 渲染含关键事件/冲突/担忧/跨日引用。"""
    digest = DiaryDigest(
        digest_type="complex",
        date=date(2026, 8, 12),
        source="llm",
        diary=DiaryDigestPart(
            intent="emotional_support",
            emotion="焦虑",
            summary="项目受阻、与领导关系紧张。",
            temporal_refs=[TemporalRef(direction="past", date_hint="昨天", summary="和妈妈吵架")],
            key_events=["和领导争执"],
            emotional_shifts=["平静", "焦虑"],
            relationships=[DigestEntity(name="李总", relation="领导", sentiment=-0.6)],
            conflicts=["想推进项目但被否决"],
            concerns=["担心延期影响晋升"],
        ),
    )
    upsert_digest(db_session, user_id="user-1", day=date(2026, 8, 12), digest=digest)
    db_session.commit()

    text = format_day_digest(db_session, user_id="user-1", day=date(2026, 8, 12))
    assert "提及非当日" in text
    assert "和妈妈吵架" in text
    assert "关键事件：和领导争执" in text
    assert "情绪变化：平静 → 焦虑" in text
    assert "人物关系：李总(领导)" in text
    assert "冲突：想推进项目但被否决" in text
    assert "担忧：担心延期影响晋升" in text
