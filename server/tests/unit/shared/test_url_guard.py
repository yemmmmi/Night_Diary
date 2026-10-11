"""Unit tests for the outbound-URL / path guard (C5)."""

from __future__ import annotations

import pytest

from app.shared import url_guard
from app.shared.url_guard import (
    ALLOWED_HF_HOSTS,
    safe_join,
    validate_outbound_url,
)


class TestValidateOutboundUrl:
    def test_empty_url_rejected(self) -> None:
        assert validate_outbound_url("") is not None
        assert validate_outbound_url("   ") is not None

    def test_non_http_scheme_rejected(self) -> None:
        assert validate_outbound_url("ftp://8.8.8.8/x") is not None
        assert validate_outbound_url("file:///etc/passwd") is not None

    def test_missing_host_rejected(self) -> None:
        assert validate_outbound_url("http://") is not None

    def test_embedded_credentials_rejected(self) -> None:
        err = validate_outbound_url("https://user:pass@8.8.8.8/v1")
        assert err is not None
        assert "账号密码" in err

    def test_public_ip_allowed(self) -> None:
        assert validate_outbound_url("https://8.8.8.8/v1") is None

    def test_metadata_address_always_blocked(self) -> None:
        err = validate_outbound_url("http://169.254.169.254/latest/meta-data")
        assert err is not None
        assert "元数据" in err

    def test_loopback_allowed_by_default(self) -> None:
        assert validate_outbound_url("http://127.0.0.1:11434/v1") is None

    def test_loopback_blocked_when_private_disallowed(self) -> None:
        err = validate_outbound_url("http://127.0.0.1:11434/v1", allow_private=False)
        assert err is not None
        assert "内网" in err

    def test_ipv6_loopback_blocked_when_private_disallowed(self) -> None:
        assert validate_outbound_url("http://[::1]:8000/v1", allow_private=False) is not None

    def test_host_allowlist_rejects_unknown_host(self) -> None:
        err = validate_outbound_url("https://evil.example.com/models", allow_hosts=ALLOWED_HF_HOSTS)
        assert err is not None
        assert "允许列表" in err

    def test_host_allowlist_accepts_subdomain(self, monkeypatch) -> None:
        monkeypatch.setattr(url_guard, "_resolve_host_ips", lambda host: [])
        assert (
            validate_outbound_url("https://www.hf-mirror.com", allow_hosts=ALLOWED_HF_HOSTS) is None
        )

    def test_host_allowlist_accepts_exact_host(self, monkeypatch) -> None:
        monkeypatch.setattr(url_guard, "_resolve_host_ips", lambda host: [])
        assert validate_outbound_url("https://hf-mirror.com", allow_hosts=ALLOWED_HF_HOSTS) is None


class TestSafeJoin:
    def test_joins_within_root(self, tmp_path) -> None:
        result = safe_join(tmp_path, ".ready", "BAAI--bge-small-zh-v1.5")
        assert result == (tmp_path / ".ready" / "BAAI--bge-small-zh-v1.5").resolve()

    def test_rejects_traversal_escape(self, tmp_path) -> None:
        with pytest.raises(ValueError):
            safe_join(tmp_path, "..", "outside")

    def test_rejects_absolute_escape(self, tmp_path) -> None:
        with pytest.raises(ValueError):
            safe_join(tmp_path, "..", "..", "etc")
