"""Route tests for the Memory Library API — user-authored 「关于我」 (B2)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_about_defaults_to_empty(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/memory/about")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == ""
    assert body["updated_at"] == 0.0
    assert body["max_chars"] > 0


def test_put_about_roundtrip_strips_whitespace(authed_client: TestClient) -> None:
    resp = authed_client.put(
        "/api/v1/memory/about",
        json={"content": "  我是夜班护士，希望语气温和一点。  "},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "我是夜班护士，希望语气温和一点。"
    assert body["updated_at"] > 0

    resp = authed_client.get("/api/v1/memory/about")
    assert resp.json()["content"] == "我是夜班护士，希望语气温和一点。"


def test_put_about_rejects_over_limit(authed_client: TestClient) -> None:
    resp = authed_client.put("/api/v1/memory/about", json={"content": "x" * 5000})
    assert resp.status_code == 422


def test_about_is_user_scoped(
    api_client: TestClient, two_users: tuple[dict, dict]
) -> None:
    headers_a, headers_b = two_users
    api_client.put(
        "/api/v1/memory/about", json={"content": "Alice 的自述"}, headers=headers_a
    )
    api_client.put(
        "/api/v1/memory/about", json={"content": "Bob 的自述"}, headers=headers_b
    )

    resp_a = api_client.get("/api/v1/memory/about", headers=headers_a)
    resp_b = api_client.get("/api/v1/memory/about", headers=headers_b)
    assert resp_a.json()["content"] == "Alice 的自述"
    assert resp_b.json()["content"] == "Bob 的自述"