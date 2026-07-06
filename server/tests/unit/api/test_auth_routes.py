"""Tests for authentication routes: register, login, me."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestRegister:
    def test_register_success(self, api_client: TestClient):
        resp = api_client.post(
            "/api/v1/auth/register",
            json={"email": "new@test.com", "password": "password123", "nickname": "NewUser"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@test.com"
        assert body["nickname"] == "NewUser"
        assert body["is_active"] is True
        assert "id" in body
        assert "password_hash" not in body
        assert "password" not in body

    def test_register_duplicate_email(self, api_client: TestClient):
        api_client.post(
            "/api/v1/auth/register",
            json={"email": "dup@test.com", "password": "password123"},
        )
        resp = api_client.post(
            "/api/v1/auth/register",
            json={"email": "dup@test.com", "password": "password456"},
        )
        assert resp.status_code == 409

    def test_register_invalid_email(self, api_client: TestClient):
        resp = api_client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "password123"},
        )
        assert resp.status_code == 422

    def test_register_short_password(self, api_client: TestClient):
        resp = api_client.post(
            "/api/v1/auth/register",
            json={"email": "short@test.com", "password": "12345"},
        )
        assert resp.status_code == 422

    def test_register_default_nickname(self, api_client: TestClient):
        """Nickname defaults to the email local part when omitted."""
        resp = api_client.post(
            "/api/v1/auth/register",
            json={"email": "myname@test.com", "password": "password123"},
        )
        assert resp.status_code == 201
        assert resp.json()["nickname"] == "myname"


class TestLogin:
    def test_login_success(self, api_client: TestClient):
        api_client.post(
            "/api/v1/auth/register",
            json={"email": "login@test.com", "password": "password123"},
        )
        resp = api_client.post(
            "/api/v1/auth/login",
            data={"username": "login@test.com", "password": "password123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "login@test.com"

    def test_login_wrong_password(self, api_client: TestClient):
        api_client.post(
            "/api/v1/auth/register",
            json={"email": "wrong@test.com", "password": "password123"},
        )
        resp = api_client.post(
            "/api/v1/auth/login",
            data={"username": "wrong@test.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, api_client: TestClient):
        resp = api_client.post(
            "/api/v1/auth/login",
            data={"username": "ghost@test.com", "password": "password123"},
        )
        assert resp.status_code == 401


class TestMe:
    def test_me_success(self, api_client: TestClient, auth_headers: dict):
        resp = api_client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "alice@test.com"

    def test_me_no_token(self, api_client: TestClient):
        resp = api_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, api_client: TestClient):
        resp = api_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_me_expired_token(self, api_client: TestClient):
        """A token signed with a different secret should be rejected."""
        # Create a token with a wrong secret
        import jwt as pyjwt

        bad_token = pyjwt.encode(
            {"sub": "1"},
            "wrong-secret-key-different-from-config",
            algorithm="HS256",
        )
        resp = api_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        assert resp.status_code == 401
