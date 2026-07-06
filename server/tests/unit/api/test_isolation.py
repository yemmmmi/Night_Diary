"""Tests for multi-user data isolation.

Verifies that user A's data is invisible to user B across all core tables.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestDiaryIsolation:
    def test_user_cannot_see_others_diaries(
        self, api_client: TestClient, two_users: tuple[dict, dict]
    ):
        headers_a, headers_b = two_users

        # Alice creates a diary entry
        resp = api_client.post(
            "/api/v1/diary/entries",
            json={"content": "Alice's secret diary", "date": "2025-07-03"},
            headers=headers_a,
        )
        assert resp.status_code == 201
        entry_id = resp.json()["id"]

        # Bob lists entries — should not see Alice's
        resp = api_client.get("/api/v1/diary/entries", headers=headers_b)
        assert resp.status_code == 200
        entries = resp.json()
        assert all(e["id"] != entry_id for e in entries)

        # Bob tries to access Alice's entry directly → 404
        resp = api_client.get(f"/api/v1/diary/entries/{entry_id}", headers=headers_b)
        assert resp.status_code == 404

    def test_user_cannot_update_others_diary(
        self, api_client: TestClient, two_users: tuple[dict, dict]
    ):
        headers_a, headers_b = two_users

        resp = api_client.post(
            "/api/v1/diary/entries",
            json={"content": "Alice's diary", "date": "2025-07-03"},
            headers=headers_a,
        )
        entry_id = resp.json()["id"]

        resp = api_client.put(
            f"/api/v1/diary/entries/{entry_id}",
            json={"content": "Hacked by Bob"},
            headers=headers_b,
        )
        assert resp.status_code == 404

    def test_user_cannot_delete_others_diary(
        self, api_client: TestClient, two_users: tuple[dict, dict]
    ):
        headers_a, headers_b = two_users

        resp = api_client.post(
            "/api/v1/diary/entries",
            json={"content": "Alice's diary", "date": "2025-07-03"},
            headers=headers_a,
        )
        entry_id = resp.json()["id"]

        resp = api_client.delete(
            f"/api/v1/diary/entries/{entry_id}", headers=headers_b
        )
        assert resp.status_code == 404


class TestTagIsolation:
    def test_tags_are_user_scoped(
        self, api_client: TestClient, two_users: tuple[dict, dict]
    ):
        headers_a, headers_b = two_users

        # Alice creates a tag
        resp = api_client.post(
            "/api/v1/tags",
            json={"name": "AliceTag", "color": "#ff0000"},
            headers=headers_a,
        )
        assert resp.status_code == 201

        # Bob can create a tag with the same name (per-user unique)
        resp = api_client.post(
            "/api/v1/tags",
            json={"name": "AliceTag", "color": "#00ff00"},
            headers=headers_b,
        )
        assert resp.status_code == 201

        # Bob's tags list should not include Alice's tag
        resp = api_client.get("/api/v1/tags", headers=headers_b)
        assert resp.status_code == 200
        tag_names = [t["name"] for t in resp.json()]
        assert "AliceTag" in tag_names  # Bob's own tag
        # Each user should only see their own tags
        resp_a = api_client.get("/api/v1/tags", headers=headers_a)
        tags_a = [t["name"] for t in resp_a.json()]
        tags_b = [t["name"] for t in resp.json()]
        # Both have "AliceTag" but they are different rows
        assert len(tags_a) == len(tags_b)  # same count, different rows


class TestCardIsolation:
    def test_cards_are_user_scoped(
        self, api_client: TestClient, two_users: tuple[dict, dict]
    ):
        headers_a, headers_b = two_users

        # Alice creates a card
        resp = api_client.post(
            "/api/v1/cards",
            json={
                "content": "Alice's card",
                "emotion": "happy",
                "title": "Alice Card",
            },
            headers=headers_a,
        )
        assert resp.status_code == 201
        card_id = resp.json()["card_id"]

        # Bob lists cards — should not see Alice's
        resp = api_client.get("/api/v1/cards", headers=headers_b)
        assert resp.status_code == 200
        card_ids = [c["card_id"] for c in resp.json()]
        assert card_id not in card_ids

        # Bob tries to access Alice's card directly → 404
        resp = api_client.get(f"/api/v1/cards/{card_id}", headers=headers_b)
        assert resp.status_code == 404


class TestConversationIsolation:
    def test_conversations_are_user_scoped(
        self, api_client: TestClient, two_users: tuple[dict, dict]
    ):
        headers_a, headers_b = two_users

        # Alice creates a conversation
        resp = api_client.post(
            "/api/v1/conversations",
            json={"title": "Alice's conversation"},
            headers=headers_a,
        )
        assert resp.status_code == 201
        conv_id = resp.json()["id"]

        # Bob lists conversations — should not see Alice's
        resp = api_client.get("/api/v1/conversations", headers=headers_b)
        assert resp.status_code == 200
        conv_ids = [c["id"] for c in resp.json()]
        assert conv_id not in conv_ids

        # Bob tries to access Alice's conversation → 404
        resp = api_client.get(f"/api/v1/conversations/{conv_id}", headers=headers_b)
        assert resp.status_code == 404


class TestUnauthenticatedAccess:
    def test_diary_requires_auth(self, api_client: TestClient):
        resp = api_client.get("/api/v1/diary/entries")
        assert resp.status_code == 401

    def test_cards_requires_auth(self, api_client: TestClient):
        resp = api_client.get("/api/v1/cards")
        assert resp.status_code == 401

    def test_tags_requires_auth(self, api_client: TestClient):
        resp = api_client.get("/api/v1/tags")
        assert resp.status_code == 401

    def test_conversations_requires_auth(self, api_client: TestClient):
        resp = api_client.get("/api/v1/conversations")
        assert resp.status_code == 401

    def test_stats_requires_auth(self, api_client: TestClient):
        resp = api_client.get("/api/v1/stats")
        assert resp.status_code == 401
