"""Unit tests for MCP configuration parsing."""

from __future__ import annotations

from app.services.ai.mcp_config import StdioSpec, parse_endpoints, parse_stdios


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
