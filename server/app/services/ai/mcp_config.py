"""Parse MCP endpoint / stdio-server configuration strings."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

# Trailing "key=value" tokens in a stdio spec become child-process env vars.
# Leading dashes (CLI options) are explicitly excluded.
_ENV_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S+$")

# Only these parent-process variables are forwarded to a stdio MCP child. The
# child is a third-party server, so it must never inherit LLM/DB credentials.
SAFE_ENV_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "HOME",
        "USERPROFILE",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TEMP",
        "TMP",
        "TMPDIR",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "PYTHONUNBUFFERED",
    }
)

# Defence in depth: even a whitelisted name is dropped if it looks like a secret.
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)


def build_child_env(
    spec_env: Mapping[str, str] | None = None,
    *,
    parent_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the environment for a stdio MCP child process.

    Starts from a strict whitelist of ``parent_env`` (defaults to
    ``os.environ``), drops any secret-looking name as defence in depth, then
    layers the endpoint's explicitly declared variables on top. The result is
    always a concrete mapping, so a child never inherits the full parent
    environment (which would leak ``LLM_API_KEY``, DB credentials, ...).
    """
    parent = parent_env if parent_env is not None else os.environ
    env = {
        key: value
        for key, value in parent.items()
        if key in SAFE_ENV_KEYS and not _SECRET_NAME.search(key)
    }
    if spec_env:
        env.update(spec_env)
    return env


@dataclass(frozen=True, slots=True)
class StdioSpec:
    """One stdio MCP server: command + args + extra env for the child process."""

    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)


def _alias_from_url(url: str) -> str:
    rest = url.split("://", 1)[1]
    return rest.split("/", 1)[0]


def parse_endpoints(raw: str) -> dict[str, str]:
    """Parse MCP_ENDPOINTS: ``alias:url,alias:url`` -> ``{alias: url}``.

    Plain URLs (legacy format without an alias prefix) get an alias derived
    from host:port. Malformed entries are skipped individually — one bad
    entry never blocks the rest.
    """
    result: dict[str, str] = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        if entry.startswith(("http://", "https://")):
            alias, url = _alias_from_url(entry), entry
        elif ":" in entry:
            alias, url = entry.split(":", 1)
            alias, url = alias.strip(), url.strip()
        else:
            continue
        if alias and url:
            result[alias] = url
    return result


def parse_stdios(raw: str) -> dict[str, StdioSpec]:
    """Parse MCP_STDIOS: ``alias:command arg key=value`` -> ``{alias: StdioSpec}``.

    Entries are whitespace-split (paths with spaces are unsupported — use
    commands on PATH). Trailing ``key=value`` tokens become env vars for the
    child process.
    """
    result: dict[str, StdioSpec] = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        alias, rest = entry.split(":", 1)
        alias = alias.strip()
        tokens = rest.split()
        if not alias or not tokens:
            continue
        command, args = tokens[0], tokens[1:]
        env: dict[str, str] = {}
        while args and _ENV_TOKEN.match(args[-1]):
            key, value = args.pop().split("=", 1)
            env[key] = value
        result[alias] = StdioSpec(command=command, args=tuple(args), env=env)
    return result
