"""Unit tests for image upload API routes (B5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-image-payload"


def _upload(client: TestClient, *, filename: str = "海边.png", content_type: str = "image/png"):
    return client.post(
        "/api/v1/uploads/images",
        files={"file": (filename, _PNG_BYTES, content_type)},
    )


def test_upload_then_fetch_metadata_and_file(authed_client: TestClient) -> None:
    created = _upload(authed_client)
    assert created.status_code == 201
    body = created.json()
    assert body["id"] > 0
    assert body["original_filename"] == "海边.png"
    assert body["mime_type"] == "image/png"
    assert body["size_bytes"] == len(_PNG_BYTES)

    meta = authed_client.get(f"/api/v1/uploads/images/{body['id']}")
    assert meta.status_code == 200
    assert meta.json()["id"] == body["id"]

    raw = authed_client.get(f"/api/v1/uploads/images/{body['id']}/file")
    assert raw.status_code == 200
    assert raw.content == _PNG_BYTES
    assert raw.headers["content-type"] == "image/png"


def test_upload_rejects_unsupported_mime(authed_client: TestClient) -> None:
    response = _upload(authed_client, filename="note.txt", content_type="text/plain")
    assert response.status_code == 415


def test_upload_rejects_empty_file(authed_client: TestClient) -> None:
    response = authed_client.post(
        "/api/v1/uploads/images",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert response.status_code == 400


def test_upload_rejects_oversized_file(authed_client: TestClient) -> None:
    oversized = b"\x00" * (10 * 1024 * 1024 + 1)
    response = authed_client.post(
        "/api/v1/uploads/images",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert response.status_code == 413


def test_get_missing_asset_returns_404(authed_client: TestClient) -> None:
    assert authed_client.get("/api/v1/uploads/images/9999").status_code == 404
    assert authed_client.get("/api/v1/uploads/images/9999/file").status_code == 404


def test_assets_are_user_scoped(api_client: TestClient, two_users) -> None:
    headers_a, headers_b = two_users
    created = api_client.post(
        "/api/v1/uploads/images",
        files={"file": ("mine.png", _PNG_BYTES, "image/png")},
        headers=headers_a,
    )
    assert created.status_code == 201
    asset_id = created.json()["id"]

    assert api_client.get(f"/api/v1/uploads/images/{asset_id}", headers=headers_a).status_code == 200
    assert api_client.get(f"/api/v1/uploads/images/{asset_id}", headers=headers_b).status_code == 404
    assert (
        api_client.get(f"/api/v1/uploads/images/{asset_id}/file", headers=headers_b).status_code
        == 404
    )