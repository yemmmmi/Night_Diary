"""Minimal fake MCP stdio server for tests.

Speaks newline-delimited JSON-RPC over stdin/stdout (the MCP stdio
transport). Usage: python fake_mcp_stdio.py [die_after] [sleep_secs]
- die_after: exit(1) once tool calls exceed this count (0 = never die)
- sleep_secs: sleep this long before answering each tools/call
"""

from __future__ import annotations

import json
import sys
import time

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the input text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "fail",
        "description": "Always fails",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> None:
    die_after = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sleep_secs = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    calls = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fake", "version": "0.1"},
                    },
                }
            )
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            calls += 1
            if die_after and calls > die_after:
                sys.exit(1)
            if sleep_secs:
                time.sleep(sleep_secs)
            args = msg.get("params", {}).get("arguments", {})
            text = args.get("text", "")
            send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"echo: {text}"}],
                        "isError": False,
                    },
                }
            )


if __name__ == "__main__":
    main()
