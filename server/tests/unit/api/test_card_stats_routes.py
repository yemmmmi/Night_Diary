"""Card stats routes: mood-trends query parameter wiring."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_mood_trends_rejects_one_sided_date_range(authed_client: TestClient) -> None:
    response = authed_client.get(
        "/api/v1/cards/stats/mood-trends", params={"date_from": "2026-08-01"}
    )
    assert response.status_code == 422


def test_mood_trends_accepts_full_date_range(authed_client: TestClient) -> None:
    response = authed_client.get(
        "/api/v1/cards/stats/mood-trends",
        params={"date_from": "2020-01-01", "date_to": "2020-01-07"},
    )
    assert response.status_code == 200
    assert response.json() == []
