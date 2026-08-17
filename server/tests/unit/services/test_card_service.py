"""Unit tests for memory card emotions (multi-emotion support)."""

from __future__ import annotations

from app.services import card_service


# ── V3 tree-hole: card writes refresh the day digest (zero LLM) ─────────


def test_create_card_refreshes_day_digest(db_session) -> None:
    """卡片创建后，当日 digest 的 cards 段自动聚合。"""
    from app.services.digest_service import get_digest

    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="焦虑",
        emotions=["焦虑", "疲惫"],
        event_summary="加班到很晚",
        tags=["加班"],
        mood_score=0.3,
    )

    digest = get_digest(db_session, user_id="default", day=row.created_at.date())
    assert digest is not None
    assert digest.digest_type == "basic"
    assert digest.source == "card"
    assert len(digest.cards) == 1
    assert digest.cards[0].emotion == "焦虑"
    assert digest.cards[0].summary == "加班到很晚"
    assert digest.cards[0].tags == ["加班"]


def test_update_card_re_aggregates_day_digest(db_session) -> None:
    """卡片编辑后，当日 digest 的 cards 段反映最新内容。"""
    from app.services.digest_service import get_digest

    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="焦虑",
        event_summary="加班到很晚",
        tags=["加班"],
    )
    card_service.update_card(
        db_session,
        row.card_id,
        user_id="default",
        emotion="平静",
        event_summary="其实也没那么糟",
        tags=["加班", "想通"],
    )

    digest = get_digest(db_session, user_id="default", day=row.created_at.date())
    assert digest is not None
    assert len(digest.cards) == 1
    assert digest.cards[0].emotion == "平静"
    assert digest.cards[0].summary == "其实也没那么糟"
    assert digest.cards[0].tags == ["加班", "想通"]


def test_delete_card_removes_from_day_digest(db_session) -> None:
    """卡片删除后，当日 digest 的 cards 段不再包含该卡。"""
    from app.services.digest_service import get_digest

    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="焦虑",
        event_summary="加班到很晚",
    )
    card_service.delete_card(db_session, row.card_id, user_id="default")

    digest = get_digest(db_session, user_id="default", day=row.created_at.date())
    assert digest is not None
    assert digest.cards == []


def test_create_card_stores_multiple_emotions(db_session) -> None:
    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="开心",
        emotions=["开心", "悲伤"],
        event_summary="毕业典礼，既高兴又不舍",
        mood_score=0.5,
    )
    data = card_service.row_to_dict(row)

    assert data["emotion"] == "开心"  # primary stays single-valued
    assert data["emotions"] == ["开心", "悲伤"]


def test_create_card_without_emotions_falls_back_to_single(db_session) -> None:
    row = card_service.create_card(db_session, user_id="default", emotion="平静")
    data = card_service.row_to_dict(row)

    assert data["emotion"] == "平静"
    assert data["emotions"] == ["平静"]


def test_create_card_uses_first_emotion_when_primary_blank_in_list(db_session) -> None:
    row = card_service.create_card(
        db_session, user_id="default", emotion="兴奋", emotions=["兴奋", "焦虑"]
    )
    assert row.emotion == "兴奋"
    assert card_service.row_to_dict(row)["emotions"] == ["兴奋", "焦虑"]


def test_update_card_replaces_emotions(db_session) -> None:
    row = card_service.create_card(db_session, user_id="default", emotion="开心", emotions=["开心"])
    updated = card_service.update_card(
        db_session,
        row.card_id,
        user_id="default",
        emotions=["平静", "感激"],
    )
    data = card_service.row_to_dict(updated)

    assert data["emotion"] == "平静"
    assert data["emotions"] == ["平静", "感激"]


def test_update_card_single_emotion_syncs_emotions_list(db_session) -> None:
    row = card_service.create_card(
        db_session, user_id="default", emotion="开心", emotions=["开心", "悲伤"]
    )
    updated = card_service.update_card(db_session, row.card_id, user_id="default", emotion="疲惫")
    data = card_service.row_to_dict(updated)

    assert data["emotion"] == "疲惫"
    assert data["emotions"] == ["疲惫"]


def test_card_to_episodic_multi_emotion_no_interpretive_label(db_session) -> None:
    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="开心",
        emotions=["开心", "悲伤"],
        event_summary="搬家",
        importance=0.8,
    )
    entry = card_service.card_to_episodic(row)

    assert entry.emotion == "开心"
    assert entry.event_summary == "搬家"
    assert "悲喜参半" not in entry.event_summary


def test_card_to_episodic_single_emotion(db_session) -> None:
    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="平静",
        emotions=["平静"],
        event_summary="散步",
        importance=0.8,
    )
    entry = card_service.card_to_episodic(row)

    assert "悲喜参半" not in entry.event_summary
    assert entry.event_summary == "散步"


def test_expand_to_diary_links_card_without_template_body(db_session) -> None:
    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="平静",
        emotions=["平静", "期待"],
        event_summary="傍晚在河边散步",
        tags=["休息"],
    )

    diary, analysis = card_service.expand_to_diary(db_session, row.card_id, user_id="default")
    db_session.refresh(row)

    # Content is pre-populated from card's event_summary
    assert diary.content == "傍晚在河边散步"
    assert row.diary_id == diary.id
    # No container passed → no auto-analysis
    assert analysis is None


def test_expand_to_diary_pre_populates_content_from_event_summary(db_session) -> None:
    """Card's event_summary becomes diary content for immediate analysis."""
    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="开心",
        event_summary="今天和朋友聚餐",
    )
    diary, _ = card_service.expand_to_diary(db_session, row.card_id, user_id="default")
    assert diary.content == "今天和朋友聚餐"


def test_expand_to_diary_generates_content_when_no_event_summary(db_session) -> None:
    """When card has no event_summary, generate minimal content from emotion."""
    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="焦虑",
        event_summary=None,
    )
    diary, _ = card_service.expand_to_diary(db_session, row.card_id, user_id="default")
    assert "焦虑" in diary.content
    assert len(diary.content) > 0


def test_expand_to_diary_auto_analysis_best_effort(db_session) -> None:
    """Auto-analysis failure should not block the expand operation."""
    row = card_service.create_card(
        db_session,
        user_id="default",
        emotion="平静",
        event_summary="测试内容",
    )
    # Pass a fake container that will cause trigger_analysis to fail
    # — the expand should still succeed
    diary, analysis = card_service.expand_to_diary(
        db_session, row.card_id, user_id="default", container=object()
    )
    assert diary.content == "测试内容"
    # analysis is None because the fake container doesn't have build_execution_planner
    assert analysis is None
