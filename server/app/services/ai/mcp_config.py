"""Parse MCP endpoint / stdio-server configuration strings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Trailing "key=value" tokens in a stdio spec become child-process env vars.
# Leading dashes (CLI options) are explicitly excluded.
_ENV_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S+$")


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
