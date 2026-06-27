"""Unit tests for memory card emotions (multi-emotion support)."""

from __future__ import annotations

from app.services import card_service


def test_create_card_stores_multiple_emotions(db_session) -> None:
    row = card_service.create_card(
        db_session,
        emotion="开心",
        emotions=["开心", "悲伤"],
        event_summary="毕业典礼，既高兴又不舍",
        mood_score=0.5,
    )
    data = card_service.row_to_dict(row)

    assert data["emotion"] == "开心"  # primary stays single-valued
    assert data["emotions"] == ["开心", "悲伤"]


def test_create_card_without_emotions_falls_back_to_single(db_session) -> None:
    row = card_service.create_card(db_session, emotion="平静")
    data = card_service.row_to_dict(row)

    assert data["emotion"] == "平静"
    assert data["emotions"] == ["平静"]


def test_create_card_uses_first_emotion_when_primary_blank_in_list(db_session) -> None:
    row = card_service.create_card(db_session, emotion="兴奋", emotions=["兴奋", "焦虑"])
    assert row.emotion == "兴奋"
    assert card_service.row_to_dict(row)["emotions"] == ["兴奋", "焦虑"]


def test_update_card_replaces_emotions(db_session) -> None:
    row = card_service.create_card(db_session, emotion="开心", emotions=["开心"])
    updated = card_service.update_card(
        db_session,
        row.card_id,
        emotions=["平静", "感激"],
    )
    data = card_service.row_to_dict(updated)

    assert data["emotion"] == "平静"
    assert data["emotions"] == ["平静", "感激"]


def test_update_card_single_emotion_syncs_emotions_list(db_session) -> None:
    row = card_service.create_card(db_session, emotion="开心", emotions=["开心", "悲伤"])
    updated = card_service.update_card(db_session, row.card_id, emotion="疲惫")
    data = card_service.row_to_dict(updated)

    assert data["emotion"] == "疲惫"
    assert data["emotions"] == ["疲惫"]


def test_card_to_episodic_multi_emotion_no_interpretive_label(db_session) -> None:
    row = card_service.create_card(
        db_session,
        emotion="开心",
        emotions=["开心", "悲伤"],
        event_summary="搬家",
        importance=0.8,
    )
    entry = card_service.card_to_episodic(row)

    assert entry.emotion == "开心"
    assert entry.event == "搬家"
    assert "悲喜参半" not in entry.event


def test_card_to_episodic_single_emotion(db_session) -> None:
    row = card_service.create_card(
        db_session,
        emotion="平静",
        emotions=["平静"],
        event_summary="散步",
        importance=0.8,
    )
    entry = card_service.card_to_episodic(row)

    assert "悲喜参半" not in entry.event
    assert entry.event == "散步"


def test_expand_to_diary_links_card_without_template_body(db_session) -> None:
    row = card_service.create_card(
        db_session,
        emotion="平静",
        emotions=["平静", "期待"],
        event_summary="傍晚在河边散步",
        tags=["休息"],
    )

    diary = card_service.expand_to_diary(db_session, row.card_id)
    db_session.refresh(row)

    assert diary.content == ""
    assert "💭" not in diary.content
    assert "心情" not in diary.content
    assert row.diary_id == diary.id
