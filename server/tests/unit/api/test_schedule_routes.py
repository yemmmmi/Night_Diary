"""Route tests for the scheduled-task API (A4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def no_enqueue(monkeypatch):
    """Capture enqueued jobs instead of spawning worker threads."""
    calls: list[tuple] = []

    def _fake(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return "job-id"

    monkeypatch.setattr("app.infrastructure.task_queue.enqueue_task", _fake)
    return calls


def test_list_kinds(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/schedules/kinds")
    assert resp.status_code == 200
    items = {item["kind"]: item for item in resp.json()}
    assert {"daily_review", "weekly_insight", "plan_reminder"} <= set(items)
    assert items["daily_review"]["default_mode"] == "script"
    assert set(items["daily_review"]["allowed_modes"]) == {"script", "agent"}
    assert items["weekly_insight"]["default_mode"] == "agent"
    assert items["plan_reminder"]["allowed_modes"] == ["script"]


def test_create_and_list(authed_client: TestClient) -> None:
    resp = authed_client.post(
        "/api/v1/schedules",
        json={"kind": "daily_review", "cron_expr": "0 22 * * *"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind_label"] == "每日回顾"
    assert body["next_run_at"] is not None
    assert body["mode"] == "script"
    assert body["mode_label"] == "纯数据（零 LLM）"
    assert body["sink"] == "inbox"

    listing = authed_client.get("/api/v1/schedules")
    assert listing.status_code == 200
    assert [t["id"] for t in listing.json()] == [body["id"]]


def test_create_with_explicit_mode(authed_client: TestClient) -> None:
    resp = authed_client.post(
        "/api/v1/schedules",
        json={"kind": "daily_review", "cron_expr": "0 22 * * *", "mode": "agent"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["mode"] == "agent"
    assert resp.json()["mode_label"] == "生成型（走 LLM）"


def test_create_rejects_mode_not_allowed_for_kind(authed_client: TestClient) -> None:
    resp = authed_client.post(
        "/api/v1/schedules",
        json={"kind": "plan_reminder", "cron_expr": "0 9 * * *", "mode": "agent"},
    )
    assert resp.status_code == 422


def test_create_rejects_unknown_kind(authed_client: TestClient) -> None:
    resp = authed_client.post(
        "/api/v1/schedules",
        json={"kind": "bogus", "cron_expr": "0 9 * * *"},
    )
    assert resp.status_code == 422


def test_create_rejects_bad_cron(authed_client: TestClient) -> None:
    resp = authed_client.post(
        "/api/v1/schedules",
        json={"kind": "plan_reminder", "cron_expr": "every day"},
    )
    assert resp.status_code == 422


def test_update_and_delete(authed_client: TestClient) -> None:
    created = authed_client.post(
        "/api/v1/schedules",
        json={"kind": "plan_reminder", "cron_expr": "0 9 * * *"},
    ).json()

    patched = authed_client.patch(
        f"/api/v1/schedules/{created['id']}",
        json={"cron_expr": "30 8 * * *", "enabled": False},
    )
    assert patched.status_code == 200
    assert patched.json()["cron_expr"] == "30 8 * * *"
    assert patched.json()["enabled"] is False
    assert patched.json()["next_run_at"] is None

    deleted = authed_client.delete(f"/api/v1/schedules/{created['id']}")
    assert deleted.status_code == 204
    assert authed_client.get(f"/api/v1/schedules/{created['id']}").status_code == 404


def test_trigger_enqueues(authed_client: TestClient, no_enqueue) -> None:
    created = authed_client.post(
        "/api/v1/schedules",
        json={"kind": "plan_reminder", "cron_expr": "0 9 * * *"},
    ).json()

    resp = authed_client.post(f"/api/v1/schedules/{created['id']}/trigger")
    assert resp.status_code == 200
    assert len(no_enqueue) == 1


def test_runs_empty_for_new_task(authed_client: TestClient) -> None:
    created = authed_client.post(
        "/api/v1/schedules",
        json={"kind": "weekly_insight", "cron_expr": "0 20 * * 0"},
    ).json()

    resp = authed_client.get(f"/api/v1/schedules/{created['id']}/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_missing_task_returns_404(authed_client: TestClient) -> None:
    assert authed_client.get("/api/v1/schedules/missing").status_code == 404
    assert authed_client.delete("/api/v1/schedules/missing").status_code == 404