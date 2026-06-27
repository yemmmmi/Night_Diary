"""Unit tests for analysis API routes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import AnalysisResponse


def _create_diary(client: TestClient, content: str = "分析 API 测试") -> int:
    response = client.post("/api/v1/diary/entries", json={"content": content})
    assert response.status_code == 201
    return response.json()["id"]


def test_trigger_and_get_analysis(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)

    triggered = api_client.post(f"/api/v1/analysis/{diary_id}")
    assert triggered.status_code == 201
    body = triggered.json()
    assert body["diary_id"] == diary_id
    assert body["execution_tier"]
    assert body["ai_ans"]

    fetched = api_client.get(f"/api/v1/analysis/{diary_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_duplicate_analysis_returns_409(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)
    assert api_client.post(f"/api/v1/analysis/{diary_id}").status_code == 201
    duplicate = api_client.post(f"/api/v1/analysis/{diary_id}")
    assert duplicate.status_code == 409


def test_regenerate_analysis_replaces_existing(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)
    first = api_client.post(f"/api/v1/analysis/{diary_id}")
    assert first.status_code == 201

    regen = api_client.post(f"/api/v1/analysis/{diary_id}/regenerate")
    assert regen.status_code == 200
    assert regen.json()["ai_ans"]
    assert regen.json()["diary_id"] == diary_id
    assert regen.json()["ai_ans"]
    assert api_client.get(f"/api/v1/analysis/{diary_id}").status_code == 200


def test_delete_analysis_clears_reply(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)
    assert api_client.post(f"/api/v1/analysis/{diary_id}").status_code == 201

    deleted = api_client.delete(f"/api/v1/analysis/{diary_id}")
    assert deleted.status_code == 204
    assert api_client.get(f"/api/v1/analysis/{diary_id}").status_code == 404

    entry = api_client.get(f"/api/v1/diary/entries/{diary_id}")
    assert entry.status_code == 200
    assert entry.json()["ai_ans"] in (None, "")


def test_get_analysis_before_trigger_returns_404(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)
    response = api_client.get(f"/api/v1/analysis/{diary_id}")
    assert response.status_code == 404


# ── 回信者风格链路: body → style_fragment 透传到 service ────────────────


def _patch_analysis_route(monkeypatch: pytest.MonkeyPatch, diary_id: int) -> dict[str, object]:
    """Patch the analysis route's service/mapper refs to capture ``style_fragment``.

    Returns a ``captured`` dict whose ``style_fragment`` key is filled by the
    fake service call. The route's downstream ``get_entry`` / ``analysis_to_response``
    are stubbed too so the handler returns a valid 201 without booting the LLM.
    """
    import app.api.v1.analysis as route

    captured: dict[str, object] = {}

    def fake_trigger(db, did, container, *, style_fragment=None):  # type: ignore[no-untyped-def]
        captured["style_fragment"] = style_fragment
        return (object(), 0)

    def fake_regenerate(db, did, container, *, style_fragment=None):  # type: ignore[no-untyped-def]
        captured["style_fragment"] = style_fragment
        return (object(), 0)

    class _FakeEntry:
        ai_ans = "fake reply"

    def fake_get_entry(db, did):  # type: ignore[no-untyped-def]
        return _FakeEntry()

    def fake_to_response(  # type: ignore[no-untyped-def]
        row, *, ai_ans=None, db=None, referenced_memory_count=0
    ):
        return AnalysisResponse(
            id=1,
            diary_id=diary_id,
            created_at=datetime.now(UTC),
            token_cost=0,
            cache_hit_tokens=0,
            cache_miss_tokens=0,
            output_tokens=0,
            agent_mode="multi_agent",
            execution_tier="medium",
            activated_agents="",
            ai_ans=ai_ans,
            referenced_memory_count=referenced_memory_count,
        )

    monkeypatch.setattr(route.analysis_service, "trigger_analysis", fake_trigger)
    monkeypatch.setattr(route.analysis_service, "regenerate_analysis", fake_regenerate)
    monkeypatch.setattr(route.diary_service, "get_entry", fake_get_entry)
    monkeypatch.setattr(route, "analysis_to_response", fake_to_response)
    return captured


def test_trigger_passes_preset_style_fragment_to_service(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    diary_id = _create_diary(api_client)
    captured = _patch_analysis_route(monkeypatch, diary_id)

    response = api_client.post(
        f"/api/v1/analysis/{diary_id}", json={"replier_preset": "pragmatic"}
    )
    assert response.status_code == 201

    fragment = captured["style_fragment"]
    assert fragment is not None
    assert "## 回信风格（用户指定，优先级最高）" in fragment
    # pragmatic 文案的标志性词, 证明 preset 被映射成正确文案
    assert "老朋友" in fragment


def test_trigger_persona_overrides_preset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    diary_id = _create_diary(api_client)
    captured = _patch_analysis_route(monkeypatch, diary_id)

    response = api_client.post(
        f"/api/v1/analysis/{diary_id}",
        json={"replier_preset": "warm", "replier_persona": "你是一个诗人，用短句回信"},
    )
    assert response.status_code == 201

    fragment = captured["style_fragment"]
    assert fragment is not None
    assert "## 回信者人设（用户指定，优先级最高）" in fragment
    assert "你是一个诗人，用短句回信" in fragment


def test_trigger_without_body_passes_none_style_fragment(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """不带 body 的旧请求应走默认风格: style_fragment 为 None (向后兼容)。"""
    diary_id = _create_diary(api_client)
    captured = _patch_analysis_route(monkeypatch, diary_id)

    response = api_client.post(f"/api/v1/analysis/{diary_id}")
    assert response.status_code == 201
    assert captured["style_fragment"] is None


def test_regenerate_passes_preset_style_fragment_to_service(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    diary_id = _create_diary(api_client)
    captured = _patch_analysis_route(monkeypatch, diary_id)

    response = api_client.post(
        f"/api/v1/analysis/{diary_id}/regenerate", json={"replier_preset": "calm"}
    )
    assert response.status_code == 200

    fragment = captured["style_fragment"]
    assert fragment is not None
    assert "## 回信风格（用户指定，优先级最高）" in fragment
    # calm 文案的标志性词
    assert "不急不躁" in fragment
