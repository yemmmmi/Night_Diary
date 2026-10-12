"""Outbound-URL and filesystem-path guards for SSRF / traversal defence.

Two trust boundaries are covered:

* :func:`validate_outbound_url` screens a URL before the app issues an HTTP
  request to it. It enforces the ``http``/``https`` scheme, rejects embedded
  credentials, and always blocks link-local / cloud-metadata / reserved hosts.
  Loopback and RFC1918 hosts are rejected only when ``allow_private`` is False,
  because 夜记 is a local-first app where self-hosted LLM endpoints (Ollama,
  LM Studio, vLLM) legitimately live on localhost or the LAN.
* :func:`safe_join` resolves a path under an allowed root and refuses to escape
  it, covering the HuggingFace cache marker layout.

Mirrors Hermes' whitelist validation of the terminal working directory.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

#: Hosts permitted as the HuggingFace download endpoint (SSRF allow-list).
ALLOWED_HF_HOSTS: frozenset[str] = frozenset(
    {
        "huggingface.co",
        "hf.co",
        "hf-mirror.com",
    }
)

#: Ranges blocked regardless of ``allow_private``: cloud metadata + non-routable.
_ALWAYS_BLOCKED_NETS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS & GCP metadata
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ipaddress.ip_network("100.100.100.200/32"),  # Alibaba Cloud metadata
    ipaddress.ip_network("fd00:ec2::254/128"),  # AWS IPv6 metadata
    ipaddress.ip_network("0.0.0.0/32"),  # unspecified
    ipaddress.ip_network("::/128"),
)

#: Ranges blocked only when ``allow_private`` is False (loopback + RFC1918 + ULA).
_PRIVATE_NETS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def _host_allowed(host: str, allow_hosts: Iterable[str]) -> bool:
    """True when ``host`` equals or is a subdomain of an allow-listed host."""
    normalized = host.lower().rstrip(".")
    for allowed in allow_hosts:
        candidate = allowed.lower().strip().rstrip(".")
        if not candidate:
            continue
        if normalized == candidate or normalized.endswith("." + candidate):
            return True
    return False


def _resolve_host_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve ``host`` to IP addresses; IP literals short-circuit DNS."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        try:
            ips.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return ips


def _classify_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool
) -> str | None:
    """Return a block reason for ``ip``, or None when it is a permitted target."""
    if ip.is_multicast or ip.is_reserved:
        return "保留或组播地址"
    for net in _ALWAYS_BLOCKED_NETS:
        if ip in net:
            return "链路本地或云元数据地址"
    if not allow_private:
        for net in _PRIVATE_NETS:
            if ip in net:
                return "内网或回环地址"
    return None


def validate_outbound_url(
    url: str,
    *,
    allow_private: bool = True,
    allow_hosts: Iterable[str] | None = None,
) -> str | None:
    """Return an error message when ``url`` is unsafe to request, else None.

    ``allow_hosts`` restricts the target to an explicit host allow-list (used
    for the HuggingFace mirror); ``allow_private`` keeps loopback/LAN targets
    reachable for self-hosted LLM endpoints while metadata ranges stay blocked.
    """
    if not url or not url.strip():
        return "URL 为空"
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return "URL 格式错误"
    if parts.scheme not in ("http", "https"):
        return "仅支持 http/https 协议"
    host = parts.hostname
    if not host:
        return "URL 缺少主机名"
    if parts.username or parts.password:
        return "URL 不允许包含账号密码"
    if allow_hosts is not None and not _host_allowed(host, allow_hosts):
        return f"主机 {host} 不在允许列表内"
    for ip in _resolve_host_ips(host):
        reason = _classify_ip(ip, allow_private=allow_private)
        if reason is not None:
            return f"拒绝访问{reason}: {host}"
    return None


def safe_join(root: str | Path, *parts: str) -> Path:
    """Resolve ``parts`` under ``root``; raise ValueError if it escapes ``root``."""
    root_path = Path(root).resolve()
    candidate = root_path.joinpath(*parts).resolve()
    if candidate != root_path and root_path not in candidate.parents:
        raise ValueError(f"路径越界: {candidate} 不在 {root_path} 内")
    return candidate
