"""card_service.get_mood_trends 的日期窗口语义."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.services import card_service


def test_get_mood_trends_days_window(db_session) -> None:
    card_service.create_card(
        db_session, user_id="default", emotion="平静", event_summary="散步", mood_score=0.6
    )
    points = card_service.get_mood_trends(db_session, user_id="default", days=7)
    assert len(points) == 1
    assert points[0]["card_count"] == 1
    assert abs(points[0]["avg_mood"] - 0.6) < 1e-6


def test_get_mood_trends_explicit_range_overrides_days(db_session) -> None:
    card_service.create_card(
        db_session, user_id="default", emotion="开心", event_summary="聚餐", mood_score=0.9
    )
    today = datetime.now(UTC).date()
    in_range = card_service.get_mood_trends(
        db_session,
        user_id="default",
        days=7,
        date_from=today - timedelta(days=6),
        date_to=today,
    )
    assert len(in_range) == 1

    out_of_range = card_service.get_mood_trends(
        db_session,
        user_id="default",
        days=7,
        date_from=date(2020, 1, 1),
        date_to=date(2020, 1, 7),
    )
    assert out_of_range == []
