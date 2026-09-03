"""End-to-end API flow: card → expand (auto analysis) → feedback → diary CRUD."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_card_analysis_feedback_flow(e2e_client: TestClient) -> None:
    # 1. 记一笔卡片(结构化输入, 无需 LLM)
    card = e2e_client.post(
        "/api/v1/cards",
        json={
            "emotion": "开心",
            "emotions": ["开心", "期待"],
            "event_summary": "E2E 流程测试: 今天心情不错。",
            "mood_score": 0.8,
        },
    )
    assert card.status_code == 201, card.text
    card_id = card.json()["card_id"]

    # 2. 展开为日记 - 生产环境的自动分析触发路径(卡片展开)
    expand = e2e_client.post(f"/api/v1/cards/{card_id}/expand", json={})
    assert expand.status_code == 200, expand.text
    diary_id = expand.json()["diary_id"]
    analysis_id = expand.json()["analysis_id"]

    # 展开后的日记可在日记列表中查到
    listed = e2e_client.get("/api/v1/diary/entries")
    assert listed.status_code == 200
    assert any(entry["id"] == diary_id for entry in listed.json())

    # 3. 对分析结果提交反馈
    feedback = e2e_client.post(
        f"/api/v1/feedback/{analysis_id}",
        json={"feedback_type": "positive", "response_style": "empathetic"},
    )
    assert feedback.status_code == 201
    assert feedback.json()["analysis_id"] == analysis_id

    # 4. 日记更新与删除
    updated = e2e_client.put(
        f"/api/v1/diary/entries/{diary_id}",
        json={"content": "E2E 流程测试: 已更新内容。"},
    )
    assert updated.status_code == 200

    deleted = e2e_client.delete(f"/api/v1/diary/entries/{diary_id}")
    assert deleted.status_code == 204
