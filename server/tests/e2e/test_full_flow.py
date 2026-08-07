"""End-to-end API flow: diary CRUD → analysis → feedback."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_diary_analysis_feedback_flow(e2e_client: TestClient) -> None:
    created = e2e_client.post(
        "/api/v1/diary/entries",
        json={"content": "E2E 流程测试: 今天心情不错。"},
    )
    assert created.status_code == 201
    diary_id = created.json()["id"]

    listed = e2e_client.get("/api/v1/diary/entries")
    assert listed.status_code == 200
    assert any(entry["id"] == diary_id for entry in listed.json())

    analysis = e2e_client.post(f"/api/v1/analysis/{diary_id}")
    assert analysis.status_code == 201
    analysis_id = analysis.json()["id"]
    assert analysis.json()["reply"]

    feedback = e2e_client.post(
        f"/api/v1/feedback/{analysis_id}",
        json={"feedback_type": "positive", "response_style": "empathetic"},
    )
    assert feedback.status_code == 201
    assert feedback.json()["analysis_id"] == analysis_id

    updated = e2e_client.put(
        f"/api/v1/diary/entries/{diary_id}",
        json={"content": "E2E 流程测试: 已更新内容。"},
    )
    assert updated.status_code == 200

    deleted = e2e_client.delete(f"/api/v1/diary/entries/{diary_id}")
    assert deleted.status_code == 204
