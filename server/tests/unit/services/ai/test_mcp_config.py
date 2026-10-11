"""Unit tests for MCP configuration parsing."""

from __future__ import annotations

from app.services.ai.mcp_config import (
    StdioSpec,
    build_child_env,
    parse_endpoints,
    parse_stdios,
)


class TestParseEndpoints:
    def test_empty(self) -> None:
        assert parse_endpoints("") == {}
        assert parse_endpoints(" , ") == {}

    def test_alias_url_pairs(self) -> None:
        raw = "search:http://localhost:9201/sse,weather:http://localhost:9202/sse"
        assert parse_endpoints(raw) == {
            "search": "http://localhost:9201/sse",
            "weather": "http://localhost:9202/sse",
        }

    def test_plain_url_gets_alias_from_host(self) -> None:
        raw = "http://localhost:9201/sse"
        assert parse_endpoints(raw) == {"localhost:9201": "http://localhost:9201/sse"}

    def test_malformed_entries_skipped(self) -> None:
        raw = "good:http://x/sse,,no-colon-entry,bad:"
        assert parse_endpoints(raw) == {"good": "http://x/sse"}

    def test_duplicate_alias_last_wins(self) -> None:
        raw = "a:http://x/sse,a:http://y/sse"
        assert parse_endpoints(raw) == {"a": "http://y/sse"}


class TestParseStdios:
    def test_empty(self) -> None:
        assert parse_stdios("") == {}

    def test_command_with_env(self) -> None:
        raw = "tavily:uvx tavily-mcp api_key=secret"
        assert parse_stdios(raw) == {
            "tavily": StdioSpec(command="uvx", args=("tavily-mcp",), env={"api_key": "secret"}),
        }

    def test_plain_command(self) -> None:
        raw = "fetch:npx -y @modelcontextprotocol/server-fetch"
        spec = parse_stdios(raw)["fetch"]
        assert spec.command == "npx"
        assert spec.args == ("-y", "@modelcontextprotocol/server-fetch")
        assert spec.env == {}

    def test_dash_option_with_equals_not_env(self) -> None:
        raw = "a:mytool --opt=v key=1"
        spec = parse_stdios(raw)["a"]
        assert spec.args == ("--opt=v",)
        assert spec.env == {"key": "1"}

    def test_malformed_entries_skipped(self) -> None:
        raw = "no-colon, :empty-cmd"
        assert parse_stdios(raw) == {}


class TestBuildChildEnv:
    """C3: stdio MCP children must never inherit parent secrets."""

    def test_strips_secret_named_parent_vars(self) -> None:
        parent = {
            "PATH": "/usr/bin",
            "LANG": "zh_CN.UTF-8",
            "LLM_API_KEY": "sk-leak",
            "DATABASE_URL": "mysql://root:pw@db/app",
            "MYSQL_PASSWORD": "pw",
        }
        env = build_child_env(parent_env=parent)
        assert env == {"PATH": "/usr/bin", "LANG": "zh_CN.UTF-8"}
        assert "LLM_API_KEY" not in env
        assert "DATABASE_URL" not in env

    def test_only_whitelisted_parent_vars_forwarded(self) -> None:
        parent = {"PATH": "/bin", "RANDOM_VAR": "x", "HOME": "/root"}
        env = build_child_env(parent_env=parent)
        assert set(env) == {"PATH", "HOME"}

    def test_spec_env_is_layered_on_top(self) -> None:
        parent = {"PATH": "/bin"}
        env = build_child_env({"api_key": "declared"}, parent_env=parent)
        assert env["api_key"] == "declared"
        assert env["PATH"] == "/bin"

    def test_always_returns_concrete_mapping(self) -> None:
        # A concrete dict (never None) is what prevents full-env inheritance.
        assert build_child_env(parent_env={}) == {}

    def test_whitelisted_name_looking_like_secret_is_dropped(self) -> None:
        parent = {"PATH": "/bin", "TOKEN": "t"}
        env = build_child_env(parent_env=parent)
        assert "TOKEN" not in env
