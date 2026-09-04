# MCP 工具注册表（ToolRegistry）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 ToolRegistry 统一工具入口（本地 8 工具 + MCP SSE/stdio 远程工具），配 `mcp_call_logs` 持久化、Dev API 三端点、前端 MCP 标签页与 S8_mcp trace 嵌入。

**Architecture:** MCP 连接（SSE/stdio）共享一个后台 asyncio 事件循环线程（`McpLoop`），同步 `ToolFn` 通过 `run_coroutine_threadsafe` 封送；`ToolRegistry` 持有连接与命名空间工具表（`mcp__{alias}__{tool}`），`build_tool_map(user_id)` 每请求合并本地工具（按 user_id 重建）与 MCP 工具（全局共享连接 + 每请求闭包记录 user_id）；MCP 调用统一走 `call_mcp()` 完成 S8_mcp span 埋点与调用日志落库。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / `mcp` SDK（已安装）/ pytest / Vue 3 + TS + Pinia + vitest

**Spec:** `docs/superpowers/specs/2026-09-04-mcp-tool-registry-pr12.md`

---

## 对 Spec 的三处偏差（实现前发现，已论证）

1. **pid 不可得**：`mcp` SDK 的 `stdio_client` 不暴露子进程句柄，无公开 API 拿 pid。观测以 `state`（healthy/unhealthy/dead）+ `restart_count` 替代设计稿中的 pid 徽标。孤儿进程治理交给 SDK 的进程清理（`AsyncExitStack` 退出时 terminate）。
2. **必须修改 need_tools 过滤**（探索时发现的正确性问题）：`conversation_ai_service.py:652/968` 用 `intent_result.need_tools`（意图路由写死的本地工具白名单）过滤工具，`conversation_loop.py:398/653` 与 `graph_nodes.py:90` 还要求 `need_tools` 非空才启用工具调用——不修改的话 MCP 工具永远进不了 agent。修改原则：**本地工具仍按意图白名单门控，MCP 工具始终对 LLM 可用**（外部能力由 LLM 决定是否调用）。
3. **删除被取代的旧代码**：`build_tool_map_with_mcp` / `_load_mcp_tools`（tool_factory.py）从未接入业务路径，其职责被 ToolRegistry 取代，本 PR 删除（含测试）；`mcp_persistent.py` 若 grep 确认无其他引用方一并删除。旧实现还有"session 在 A 循环创建、在 B 循环使用"的跨 event-loop 隐患，新 `McpLoop` 顺带根治。

**其他实现约束：**
- `MCP_STDIOS` 条目用空白分词（`split()`），不支持带空格的路径——文档注明用 PATH 上的命令（npx/uvx/python）
- stdio 的 env 键值只识别**尾部**的 `key=value` token（避免吞掉 `--opt=v` 类参数）
- 测试环境 `mcp` 包已安装（现有 `test_mcp_persistent.py` 未 skip 直接跑）

---

## File Structure

**新建（后端）：**

| 文件 | 职责 |
|---|---|
| `server/app/services/ai/mcp_config.py` | 解析 `MCP_ENDPOINTS` / `MCP_STDIOS` 配置字符串 |
| `server/app/services/ai/mcp_connections.py` | `McpLoop`（后台事件循环）+ `McpConnection` 基类（健康/退避重启/超时）+ `SseMcpConnection` + `StdioMcpConnection` |
| `server/app/services/ai/tool_registry.py` | `ToolRegistry`：连接编排、命名空间注册、`build_tool_map` / `call_mcp` / `status` / `tools_listing` / `close` |
| `server/app/infrastructure/models/mcp_call_log.py` | `McpCallLogRow` ORM 模型 |
| `server/app/infrastructure/mcp_call_tracer.py` | `McpCallRecord` + `McpCallTracer`（落库）+ `list_calls`（查询） |
| `server/alembic/versions/010_mcp_call_logs.py` | 幂等建表迁移 |
| `server/tests/fixtures/fake_mcp_stdio.py` | 假 stdio MCP server（内联 JSON-RPC，支持 die-after / sleep 参数） |
| `server/tests/unit/services/ai/test_mcp_config.py` | 解析单测 |
| `server/tests/unit/services/ai/test_mcp_connections.py` | 连接层单测（真子进程） |
| `server/tests/unit/services/ai/test_tool_registry.py` | 注册表单测 |
| `server/tests/unit/api/test_dev_mcp_api.py` | Dev API 单测 |
| `server/tests/e2e/test_mcp_flow.py` | 全栈 e2e（真 stdio 子进程穿真实 API） |

**新建（前端）：**

| 文件 | 职责 |
|---|---|
| `src/features/dev/McpPanel.vue` | MCP 标签页（端点/工具清单/调用流水，细线列表风格） |
| `src/__tests__/McpPanel.spec.ts` | 组件测试 |

**修改（后端）：** `config.py`（+mcp_stdios）、`tool_factory.py`（动态 spec + `is_mcp_tool` + 删旧 MCP 代码）、`container.py`（+tool_registry 字段与 `ensure_tool_registry`）、`conversation_ai_service.py`（`_build_tools` 走注册表 + `_filter_tools`）、`conversation_loop.py` / `graph_nodes.py`（enable_tools 放行 MCP）、`main.py`（shutdown 关闭注册表）、`dev.py`（三端点）、`database.py` + `alembic/env.py`（模型注册）

**修改（前端）：** `src/shared/api/dev.ts`（类型 + 3 函数）、`src/pages/DevScene.vue`（顶部标签切换 链路追踪/MCP）

**修改（部署）：** `docker-compose.yml`（mcp profile + env 透传）、`server/.env.example`

**删除：** `tool_factory.py` 中 `_load_mcp_tools` + `build_tool_map_with_mcp`、`server/tests/unit/services/ai/test_mcp_tool_factory.py`、（grep 确认无引用后）`server/app/services/ai/mcp_persistent.py` + `server/tests/unit/services/ai/test_mcp_persistent.py`

---

### Task 0: 建分支

- [ ] **Step 0.1: 从 origin/main 拉新分支**

```bash
git fetch origin && git checkout -b feat/mcp-tool-registry-pr12 origin/main
```

---

### Task 1: 配置解析（mcp_config.py）

**Files:**
- Modify: `server/app/config.py`（mcp_endpoints 字段之后，约 96-101 行处）
- Create: `server/app/services/ai/mcp_config.py`
- Test: `server/tests/unit/services/ai/test_mcp_config.py`

- [ ] **Step 1.1: 写失败测试**

```python
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
```

- [ ] **Step 1.2: 运行确认失败**

```bash
cd server; python -m pytest tests/unit/services/ai/test_mcp_config.py -v
```

Expected: FAIL（ModuleNotFoundError: app.services.ai.mcp_config）

- [ ] **Step 1.3: 实现 mcp_config.py**

```python
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
```

- [ ] **Step 1.4: config.py 加 mcp_stdios 字段**

在 `server/app/config.py` 的 `mcp_endpoints` 字段（约 96-101 行）之后添加：

```python
    mcp_stdios: str = Field(
        default="",
        description="Comma-separated stdio MCP server specs "
        '(e.g. "tavily:uvx tavily-mcp api_key=xxx"). '
        "Format: alias:command arg key=value. Trailing key=value tokens "
        "become child-process env vars. Paths with spaces are unsupported.",
    )
```

- [ ] **Step 1.5: 运行确认通过**

```bash
cd server; python -m pytest tests/unit/services/ai/test_mcp_config.py -v
```

Expected: PASS（10 个用例）

- [ ] **Step 1.6: 提交**

```bash
git add server/app/services/ai/mcp_config.py server/app/config.py server/tests/unit/services/ai/test_mcp_config.py
git commit -m "feat(ai): MCP 配置解析（MCP_ENDPOINTS/MCP_STDIOS）"
```

---

### Task 2: MCP 连接层（mcp_connections.py + 假 stdio server）

**Files:**
- Create: `server/app/services/ai/mcp_connections.py`
- Create: `server/tests/fixtures/fake_mcp_stdio.py`
- Test: `server/tests/unit/services/ai/test_mcp_connections.py`

- [ ] **Step 2.1: 写假 stdio MCP server（测试夹具）**

`server/tests/fixtures/fake_mcp_stdio.py`：

```python
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
```

- [ ] **Step 2.2: 写失败测试**

`server/tests/unit/services/ai/test_mcp_connections.py`：

```python
"""Unit tests for MCP connections: shared loop, stdio lifecycle, restart."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.mcp_config import StdioSpec
from app.services.ai.mcp_connections import (
    McpCallError,
    McpLoop,
    McpTimeoutError,
    StdioMcpConnection,
)

SCRIPT = Path(__file__).parents[2] / "fixtures" / "fake_mcp_stdio.py"


@pytest.fixture()
def mcp_loop():
    loop = McpLoop()
    loop.start()
    yield loop
    loop.stop()


def _stdio_conn(loop: McpLoop, *script_args: str, **kwargs: object) -> StdioMcpConnection:
    kwargs.setdefault("restart_backoff_s", (0.05, 0.05, 0.05))
    kwargs.setdefault("call_timeout_s", 10.0)
    spec = StdioSpec(command=sys.executable, args=(str(SCRIPT), *script_args))
    return StdioMcpConnection("fake", spec, loop, **kwargs)  # type: ignore[arg-type]


class TestMcpLoop:
    def test_run_coro_executes_on_background_loop(self, mcp_loop: McpLoop) -> None:
        import asyncio

        async def _probe() -> int:
            loop_id = id(asyncio.get_running_loop())
            return loop_id

        assert mcp_loop.run_coro(_probe(), timeout=5.0) == id(mcp_loop._loop)

    def test_stop_then_run_raises(self, mcp_loop: McpLoop) -> None:
        mcp_loop.stop()
        import asyncio

        async def _noop() -> None:
            return None

        with pytest.raises(McpCallError):
            mcp_loop.run_coro(_noop(), timeout=1.0)


class TestStdioConnection:
    def test_roundtrip(self, mcp_loop: McpLoop) -> None:
        conn = _stdio_conn(mcp_loop)
        assert conn.connect() is True
        assert conn.state == "healthy"
        tools = conn.list_tools()
        assert [t.name for t in tools] == ["echo", "fail"]
        assert conn.call_tool("echo", {"text": "hi"}) == "echo: hi"

    def test_spawn_failure_is_unhealthy(self, mcp_loop: McpLoop) -> None:
        spec = StdioSpec(command="definitely-not-a-command-xyz")
        conn = StdioMcpConnection("bad", spec, mcp_loop, restart_backoff_s=(0.05,))
        assert conn.connect() is False
        assert conn.state == "unhealthy"
        assert conn.last_error

    def test_restart_after_server_crash(self, mcp_loop: McpLoop) -> None:
        conn = _stdio_conn(mcp_loop, "1")  # server dies after 1 tool call
        assert conn.connect() is True
        assert conn.call_tool("echo", {"text": "a"}) == "echo: a"
        # The server has exited; the next call must restart and retry.
        assert conn.call_tool("echo", {"text": "b"}) == "echo: b"
        assert conn.restart_count == 1

    def test_timeout_raises_after_restart_retry(self, mcp_loop: McpLoop) -> None:
        conn = _stdio_conn(mcp_loop, "999999", "30")  # sleeps 30s per call
        conn._call_timeout_s = 0.5
        assert conn.connect() is True
        with pytest.raises(McpTimeoutError):
            conn.call_tool("echo", {"text": "slow"})

    def test_close_then_call_raises_when_no_backoff(self, mcp_loop: McpLoop) -> None:
        conn = _stdio_conn(mcp_loop, restart_backoff_s=())
        assert conn.connect() is True
        conn.close()
        assert conn.state == "unhealthy"
        with pytest.raises(McpCallError):
            conn.call_tool("echo", {"text": "x"})


class TestSseConnection:
    def test_connect_and_call_with_mocks(self, mcp_loop: McpLoop) -> None:
        from app.services.ai.mcp_connections import SseMcpConnection

        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="hello")]
        mock_session.call_tool = AsyncMock(return_value=mock_resp)
        mock_session.close = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("mcp.client.sse.sse_client", return_value=mock_cm),
            patch("mcp.ClientSession", return_value=mock_session),
        ):
            conn = SseMcpConnection("fake", "http://localhost:9201/sse", mcp_loop)
            assert conn.connect() is True
            assert conn.call_tool("search", {"query": "q"}) == "hello"
            conn.close()
            mock_session.close.assert_awaited()
```

- [ ] **Step 2.3: 运行确认失败**

```bash
cd server; python -m pytest tests/unit/services/ai/test_mcp_connections.py -v
```

Expected: FAIL（ModuleNotFoundError: app.services.ai.mcp_connections）

- [ ] **Step 2.4: 实现 mcp_connections.py**

```python
"""MCP transport connections: shared background event loop + SSE/stdio clients.

The ``mcp`` SDK is asyncio-only while agent tool functions are synchronous
(``ToolFn = Callable[..., str]``), so every MCP connection marshals its async
work onto one dedicated background event loop (:class:`McpLoop`). A single
long-lived loop also avoids the "session created on loop A, used on loop B"
failure mode of ``asyncio.run`` per call.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CALL_TIMEOUT_S = 30.0
DEFAULT_CONNECT_TIMEOUT_S = 15.0
DEFAULT_RESTART_BACKOFF_S = (1.0, 2.0, 4.0)


class McpCallError(Exception):
    """MCP tool call failed (after retries)."""


class McpTimeoutError(McpCallError):
    """MCP tool call exceeded its timeout."""


class McpLoop:
    """Background asyncio event loop shared by all MCP connections."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="nd-mcp-loop", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run_coro(self, coro: Any, *, timeout: float) -> Any:
        """Run a coroutine on the background loop, blocking up to ``timeout``."""
        if self._loop is None or self._thread is None or not self._thread.is_alive():
            raise McpCallError("MCP loop not running")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except TimeoutError as exc:
            future.cancel()
            raise McpTimeoutError(f"timed out after {timeout}s") from exc

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._loop = None
        self._thread = None


class McpConnection:
    """One MCP server endpoint with health state and restart-on-failure.

    Shared-process model: each endpoint keeps ONE connection for all users;
    callers pass ``user_id`` through the tool layer for per-call logging.
    """

    transport = "sse"

    def __init__(
        self,
        alias: str,
        loop: McpLoop,
        *,
        call_timeout_s: float = DEFAULT_CALL_TIMEOUT_S,
        connect_timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S,
        restart_backoff_s: tuple[float, ...] = DEFAULT_RESTART_BACKOFF_S,
    ) -> None:
        self.alias = alias
        self.loop = loop
        self.state = "unhealthy"  # healthy | unhealthy | dead
        self.restart_count = 0
        self.last_error = ""
        self.loaded_at = ""
        self.tool_count = 0
        self._call_timeout_s = call_timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._restart_backoff_s = restart_backoff_s
        self._session: Any = None
        self._cm: Any = None

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> bool:
        """Best-effort connect (also used for lazy recovery of dead endpoints)."""
        self._close_session()
        try:
            self._session = self.loop.run_coro(self._connect(), timeout=self._connect_timeout_s)
        except Exception as exc:
            self.state = "unhealthy"
            self.last_error = str(exc)
            logger.warning("MCP connect %s (%s) failed: %s", self.alias, self.transport, exc)
            return False
        self.state = "healthy"
        self.last_error = ""
        self.loaded_at = datetime_utc_now_iso()
        return True

    def _connect(self) -> Any:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    def _close_session(self) -> None:
        session, self._session = self._session, None
        cm, self._cm = self._cm, None
        if session is not None:
            with contextlib.suppress(Exception):
                self.loop.run_coro(session.close(), timeout=5.0)
        if cm is not None:
            with contextlib.suppress(Exception):
                self.loop.run_coro(cm.__aexit__(None, None, None), timeout=5.0)

    def close(self) -> None:
        self._close_session()
        self.state = "unhealthy"

    # -- tools -------------------------------------------------------------

    def list_tools(self) -> list[Any]:
        if self._session is None:
            raise McpCallError(f"{self.alias}: not connected")
        result = self.loop.run_coro(self._session.list_tools(), timeout=self._connect_timeout_s)
        return list(result.tools)

    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        """Call once; on failure restart with backoff and retry once."""
        try:
            return self._call_once(name, args)
        except Exception as exc:
            logger.warning("MCP call %s/%s failed (%s); restarting", self.alias, name, exc)
        if not self._restart_with_backoff():
            raise McpCallError(
                f"MCP endpoint {self.alias} unavailable: {self.last_error}"
            ) from None
        return self._call_once(name, args)

    def _call_once(self, name: str, args: dict[str, Any]) -> str:
        if self._session is None:
            raise McpCallError(f"{self.alias}: not connected")
        resp = self.loop.run_coro(
            self._session.call_tool(name, args), timeout=self._call_timeout_s
        )
        texts = [c.text for c in getattr(resp, "content", []) if hasattr(c, "text")]
        return "\n".join(texts) if texts else str(resp)

    def _restart_with_backoff(self) -> bool:
        for delay in self._restart_backoff_s:
            self._close_session()
            time.sleep(delay)
            if self.connect():
                self.restart_count += 1
                return True
        self.state = "dead"
        self._close_session()
        return False


def datetime_utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


class SseMcpConnection(McpConnection):
    """HTTP/SSE transport — no child process to manage."""

    transport = "sse"

    def __init__(self, alias: str, url: str, loop: McpLoop, **kwargs: Any) -> None:
        super().__init__(alias, loop, **kwargs)
        self.url = url

    async def _connect(self) -> Any:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        cm = sse_client(self.url)
        read, write = await cm.__aenter__()
        session = ClientSession(read, write)
        await session.initialize()
        self._cm = cm
        return session


class StdioMcpConnection(McpConnection):
    """stdio transport — the ``mcp`` SDK spawns and owns the child process."""

    transport = "stdio"

    def __init__(self, alias: str, spec: Any, loop: McpLoop, **kwargs: Any) -> None:
        super().__init__(alias, loop, **kwargs)
        self.spec = spec

    async def _connect(self) -> Any:
        import os

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = {**os.environ, **self.spec.env} if self.spec.env else None
        params = StdioServerParameters(
            command=self.spec.command, args=list(self.spec.args), env=env
        )
        cm = stdio_client(params)
        read, write = await cm.__aenter__()
        session = ClientSession(read, write)
        await session.initialize()
        self._cm = cm
        return session
```

- [ ] **Step 2.5: 运行确认通过**

```bash
cd server; python -m pytest tests/unit/services/ai/test_mcp_connections.py -v
```

Expected: PASS（8 个用例；stdio 用例走真实子进程，每个 <2s）

- [ ] **Step 2.6: 提交**

```bash
git add server/app/services/ai/mcp_connections.py server/tests/fixtures/fake_mcp_stdio.py server/tests/unit/services/ai/test_mcp_connections.py
git commit -m "feat(ai): MCP 连接层——共享事件循环 + SSE/stdio 双传输 + 退避重启"
```

---

### Task 3: mcp_call_logs 持久化

**Files:**
- Create: `server/app/infrastructure/models/mcp_call_log.py`
- Create: `server/app/infrastructure/mcp_call_tracer.py`
- Create: `server/alembic/versions/010_mcp_call_logs.py`
- Modify: `server/app/infrastructure/database.py`（init_db 模型导入，约 73-97 行）
- Modify: `server/alembic/env.py`（模型导入，约 17-41 行）
- Test: `server/tests/unit/infrastructure/test_mcp_call_tracer.py`

- [ ] **Step 3.1: 写失败测试**

`server/tests/unit/infrastructure/test_mcp_call_tracer.py`：

```python
"""Unit tests for mcp_call_logs persistence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.mcp_call_tracer import McpCallRecord, McpCallTracer, list_calls


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _record(**overrides: object) -> McpCallRecord:
    fields: dict[str, object] = {
        "user_id": "u1",
        "trace_id": "t1",
        "span_id": "s1",
        "endpoint_alias": "tavily",
        "transport": "stdio",
        "tool_name": "mcp__tavily__search",
        "raw_tool_name": "search",
        "status": "success",
        "duration_ms": 123.0,
        "error_message": None,
        "arguments_snapshot": '{"query": "x"}',
        "result_snapshot": "ok",
    }
    fields.update(overrides)
    return McpCallRecord(**fields)  # type: ignore[arg-type]


class TestRecord:
    def test_writes_row(self, session_factory) -> None:
        tracer = McpCallTracer(session_factory)
        tracer.record(_record())
        with session_factory() as db:
            items, total = list_calls(db)
        assert total == 1
        assert items[0]["tool_name"] == "mcp__tavily__search"
        assert items[0]["user_id"] == "u1"

    def test_truncates_snapshots_to_2kb(self, session_factory) -> None:
        tracer = McpCallTracer(session_factory)
        big = "x" * 5000
        tracer.record(_record(arguments_snapshot=big, result_snapshot=big))
        with session_factory() as db:
            items, _ = list_calls(db)
        assert len(items[0]["arguments_snapshot"]) == 2048
        assert len(items[0]["result_snapshot"]) == 2048

    def test_write_failure_never_raises(self) -> None:
        class _Broken:
            def __call__(self) -> None:
                raise RuntimeError("session factory exploded")

        tracer = McpCallTracer(_Broken())  # type: ignore[arg-type]
        tracer.record(_record())  # must not raise


class TestListCalls:
    @pytest.fixture()
    def filled(self, session_factory):
        tracer = McpCallTracer(session_factory)
        tracer.record(_record(status="success", endpoint_alias="a", user_id="u1"))
        tracer.record(_record(status="error", endpoint_alias="b", user_id="u2"))
        tracer.record(_record(status="timeout", endpoint_alias="a", user_id="u1"))
        return session_factory

    def test_filters_and_pagination(self, filled) -> None:
        with filled() as db:
            assert list_calls(db, endpoint="a")[1] == 2
            assert list_calls(db, status="error")[1] == 1
            assert list_calls(db, user_id="u2")[1] == 1
            items, total = list_calls(db, page=1, page_size=2)
        assert total == 3
        assert len(items) == 2

    def test_empty(self, session_factory) -> None:
        with session_factory() as db:
            items, total = list_calls(db)
        assert items == []
        assert total == 0
```

- [ ] **Step 3.2: 运行确认失败**

```bash
cd server; python -m pytest tests/unit/infrastructure/test_mcp_call_tracer.py -v
```

Expected: FAIL（ModuleNotFoundError: app.infrastructure.mcp_call_tracer）

- [ ] **Step 3.3: 实现模型 `server/app/infrastructure/models/mcp_call_log.py`**

（结构镜像 `llm_call_log.py`：String(64) uuid 主键、Float 时间戳、Text 快照、索引列）

```python
"""ORM model for the ``mcp_call_logs`` table."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base

if TYPE_CHECKING:
    pass


class McpCallLogRow(Base):
    """One MCP tool call (persisted for Dev panel + observability)."""

    __tablename__ = "mcp_call_logs"
    __table_args__ = (
        Index("ix_mcp_call_logs_endpoint_alias", "endpoint_alias"),
        Index("ix_mcp_call_logs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    span_id: Mapped[str] = mapped_column(String(64), default="")
    endpoint_alias: Mapped[str] = mapped_column(String(64))
    transport: Mapped[str] = mapped_column(String(16))
    tool_name: Mapped[str] = mapped_column(String(128))
    raw_tool_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    arguments_snapshot: Mapped[str] = mapped_column(Text, default="")
    result_snapshot: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float)
```

注意：去掉上面 `if TYPE_CHECKING: pass` 残留与未用的 `DateTime`/`Integer` 导入（最终文件只导入用到的 `Float, Index, String, Text` 与 `Mapped, mapped_column`；`datetime` 若未用也不导入）。

- [ ] **Step 3.4: 实现 `server/app/infrastructure/mcp_call_tracer.py`**

```python
"""Persist MCP tool calls to ``mcp_call_logs`` (mirrors llm_call_tracer)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models.mcp_call_log import McpCallLogRow

logger = logging.getLogger(__name__)

SNAPSHOT_MAX_BYTES = 2048


@dataclass(frozen=True, slots=True)
class McpCallRecord:
    user_id: str
    trace_id: str | None
    span_id: str
    endpoint_alias: str
    transport: str
    tool_name: str
    raw_tool_name: str
    status: str
    duration_ms: float
    error_message: str | None
    arguments_snapshot: str
    result_snapshot: str


def _truncate(value: str) -> str:
    return value[:SNAPSHOT_MAX_BYTES]


class McpCallTracer:
    """Append-only writer — best-effort: failures never break tool calls."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, entry: McpCallRecord) -> None:
        try:
            with self._session_factory() as session:
                session.add(
                    McpCallLogRow(
                        id=uuid.uuid4().hex,
                        user_id=entry.user_id,
                        trace_id=entry.trace_id,
                        span_id=entry.span_id,
                        endpoint_alias=entry.endpoint_alias,
                        transport=entry.transport,
                        tool_name=entry.tool_name,
                        raw_tool_name=entry.raw_tool_name,
                        status=entry.status,
                        duration_ms=entry.duration_ms,
                        error_message=entry.error_message,
                        arguments_snapshot=_truncate(entry.arguments_snapshot),
                        result_snapshot=_truncate(entry.result_snapshot),
                        created_at=datetime.now(UTC).timestamp(),
                    )
                )
                session.commit()
        except Exception as exc:
            logger.warning("mcp_call_logs write failed: %s", exc)


def list_calls(
    db: Session,
    *,
    endpoint: str | None = None,
    status: str | None = None,
    user_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Query call logs with filters + pagination (Dev API read path)."""
    query = db.query(McpCallLogRow)
    if endpoint:
        query = query.filter(McpCallLogRow.endpoint_alias == endpoint)
    if status:
        query = query.filter(McpCallLogRow.status == status)
    if user_id:
        query = query.filter(McpCallLogRow.user_id == user_id)
    total = query.count()
    rows = (
        query.order_by(desc(McpCallLogRow.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "trace_id": row.trace_id,
            "endpoint_alias": row.endpoint_alias,
            "transport": row.transport,
            "tool_name": row.tool_name,
            "raw_tool_name": row.raw_tool_name,
            "status": row.status,
            "duration_ms": row.duration_ms,
            "error_message": row.error_message,
            "arguments_snapshot": row.arguments_snapshot,
            "result_snapshot": row.result_snapshot,
            "created_at": row.created_at,
        }
        for row in rows
    ], total
```

- [ ] **Step 3.5: 注册模型（database.py + alembic/env.py）**

`server/app/infrastructure/database.py` init_db 的模型导入块（约 73-97 行）中，按字母序在 `llm_call_log` 之后加一行：

```python
    from app.infrastructure.models import mcp_call_log as _mcp_call_log_models  # noqa: F401
```

`server/alembic/env.py` 的模型导入块（约 17-41 行）同样位置加同一行。

- [ ] **Step 3.6: 写 Alembic 迁移 `server/alembic/versions/010_mcp_call_logs.py`**

（幂等模式照抄 `002_pipeline_traces_and_trace_id.py` 的 `_table_exists` / `_index_exists` 辅助函数实现）

```python
"""Create mcp_call_logs table.

Revision ID: 010_mcp_call_logs
Revises: 009_weekly_plan_struct
Create Date: 2026-09-04

Stores one row per MCP tool call (transport, duration, snapshots) for the
Dev panel call log. Idempotent: ``init_db`` may have already created the
table via ``Base.metadata.create_all`` before Alembic runs.
"""

from alembic import op
import sqlalchemy as sa


revision = "010_mcp_call_logs"
down_revision = "009_weekly_plan_struct"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    insp = sa.inspect(bind)
    return insp.has_table(name)


def _index_exists(bind, table: str, name: str) -> bool:
    insp = sa.inspect(bind)
    return name in [idx["name"] for idx in insp.get_indexes(table)]


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "mcp_call_logs"):
        return
    op.create_table(
        "mcp_call_logs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("span_id", sa.String(length=64), nullable=False),
        sa.Column("endpoint_alias", sa.String(length=64), nullable=False),
        sa.Column("transport", sa.String(length=16), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("raw_tool_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("arguments_snapshot", sa.Text(), nullable=False),
        sa.Column("result_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mcp_call_logs_user_id", "mcp_call_logs", ["user_id"])
    op.create_index("ix_mcp_call_logs_trace_id", "mcp_call_logs", ["trace_id"])
    op.create_index("ix_mcp_call_logs_endpoint_alias", "mcp_call_logs", ["endpoint_alias"])
    op.create_index("ix_mcp_call_logs_status", "mcp_call_logs", ["status"])


def downgrade() -> None:
    op.drop_table("mcp_call_logs")
```

注意：模型里 `__table_args__` 用 `Index(...)` 与迁移的显式 `create_index` 命名保持一致（`ix_mcp_call_logs_endpoint_alias` / `ix_mcp_call_logs_status`；`user_id`/`trace_id` 用列级 `index=True` 生成的默认名 `ix_mcp_call_logs_user_id` / `ix_mcp_call_logs_trace_id`）。若 `Base.metadata.create_all` 建出的索引名与迁移不一致，以数据库实际名为准调整迁移里的 `create_index` 名称，保证幂等跳过逻辑生效。

- [ ] **Step 3.7: 运行确认通过**

```bash
cd server; python -m pytest tests/unit/infrastructure/test_mcp_call_tracer.py -v
```

Expected: PASS（7 个用例）

- [ ] **Step 3.8: 提交**

```bash
git add server/app/infrastructure/models/mcp_call_log.py server/app/infrastructure/mcp_call_tracer.py server/app/infrastructure/database.py server/alembic/env.py server/alembic/versions/010_mcp_call_logs.py server/tests/unit/infrastructure/test_mcp_call_tracer.py
git commit -m "feat(infra): mcp_call_logs 表 + 落库/查询 + alembic 010"
```

---

### Task 4: ToolRegistry + 动态 spec

**Files:**
- Create: `server/app/services/ai/tool_registry.py`
- Modify: `server/app/services/ai/tool_factory.py`（动态 spec 注册 + `is_mcp_tool` + 删 `_load_mcp_tools` / `build_tool_map_with_mcp`）
- Delete: `server/tests/unit/services/ai/test_mcp_tool_factory.py`
- Test: `server/tests/unit/services/ai/test_tool_registry.py`

- [ ] **Step 4.1: tool_factory.py 加动态 spec 与工具名判定**

在 `specs_for_names`（约 386 行）之前加：

```python
# ── Dynamic (MCP) tool specs ─────────────────────────────────────────────
# MCP tools are discovered at runtime; their specs are registered here by
# ToolRegistry so native function calling (specs_for_names) can see them.

MCP_TOOL_PREFIX = "mcp__"

_dynamic_specs: dict[str, ToolSpec] = {}


def register_dynamic_specs(specs: dict[str, ToolSpec]) -> None:
    """Register namespaced MCP tool specs for native function calling."""
    _dynamic_specs.update(specs)


def is_mcp_tool(name: str) -> bool:
    return name.startswith(MCP_TOOL_PREFIX)


def namespaced_tool_name(alias: str, raw_name: str) -> str:
    return f"{MCP_TOOL_PREFIX}{alias}__{raw_name}"
```

替换 `specs_for_names`（约 386-389 行）为：

```python
def specs_for_names(names: list[str]) -> list[ToolSpec]:
    """Filter ToolSpec list to only the named tools (built-in + MCP)."""
    all_specs = {s.name: s for s in build_tool_specs()}
    all_specs.update(_dynamic_specs)
    return [all_specs[n] for n in names if n in all_specs]
```

- [ ] **Step 4.2: 删除 tool_factory.py 中 `_load_mcp_tools`（约 392-461 行）与 `build_tool_map_with_mcp`（约 464-510 行）**

先确认引用面（应只剩测试）：

```bash
rg -n "build_tool_map_with_mcp|_load_mcp_tools|PersistentMCPConnection" server/ --type py
```

预期：仅 `tool_factory.py`、`tests/unit/services/ai/test_mcp_tool_factory.py`、`tests/unit/services/ai/test_mcp_persistent.py` 命中。删除两个函数体，随后：

```bash
git rm server/tests/unit/services/ai/test_mcp_tool_factory.py
```

`mcp_persistent.py` 若除 `_load_mcp_tools` 外无引用（上一步 grep 验证），同样删除并 `git rm server/tests/unit/services/ai/test_mcp_persistent.py server/app/services/ai/mcp_persistent.py`。若 `agent_executor.py` / `router.py` 等还有引用则保留并在 PR 描述注明。

- [ ] **Step 4.3: 写失败测试**

`server/tests/unit/services/ai/test_tool_registry.py`：

```python
"""Unit tests for ToolRegistry: namespacing, merge, call logging, spans."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.mcp_call_tracer import McpCallTracer, list_calls
from app.services.ai.tool_factory import is_mcp_tool, namespaced_tool_name
from app.services.ai.tool_registry import ToolRegistry
from app.shared.pipeline_trace import PipelineTrace, set_trace, reset_trace


class FakeConn:
    transport = "stdio"

    def __init__(self, alias: str = "fake") -> None:
        self.alias = alias
        self.state = "healthy"
        self.restart_count = 0
        self.last_error = ""
        self.loaded_at = "2026-09-04T00:00:00+00:00"
        self.tool_count = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def connect(self) -> bool:
        return True

    def list_tools(self) -> list[Any]:
        return [
            SimpleNamespace(
                name="echo",
                description="回声",
                inputSchema={"type": "object", "properties": {"text": {"type": "string"}}},
            )
        ]

    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        self.calls.append((name, args))
        return "ok"

    def close(self) -> None:
        pass


class FailingConn(FakeConn):
    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        raise RuntimeError("boom")


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _registry(session_factory, conn: FakeConn | None = None) -> tuple[ToolRegistry, FakeConn]:
    container = MagicMock()
    container._llm_for_tier.return_value = MagicMock()
    container.retriever = MagicMock()
    container.session_factory = session_factory
    settings = SimpleNamespace(mcp_endpoints="", mcp_stdios="")
    reg = ToolRegistry.__new__(ToolRegistry)  # 不启动 McpLoop（连接用 Fake）
    reg._container = container
    reg._settings = settings
    reg._loop = MagicMock()
    reg._connections = {}
    reg._mcp_tools = {}
    reg._tracer = McpCallTracer(session_factory)
    fake = conn or FakeConn()
    reg.register_connection(fake)
    return reg, fake


class TestNamespacing:
    def test_names(self) -> None:
        assert namespaced_tool_name("tavily", "search") == "mcp__tavily__search"
        assert is_mcp_tool("mcp__tavily__search") is True
        assert is_mcp_tool("search_diary") is False


class TestBuildToolMap:
    def test_local_plus_mcp(self, session_factory) -> None:
        reg, _ = _registry(session_factory)
        tools = reg.build_tool_map(user_id="u1")
        assert tools is not None
        assert "search_diary" in tools  # 本地 8 个
        assert "mcp__fake__echo" in tools  # MCP 1 个
        assert len(tools) == 9

    def test_llm_unavailable_returns_none(self, session_factory) -> None:
        reg, _ = _registry(session_factory)
        reg._container._llm_for_tier.return_value = None
        assert reg.build_tool_map(user_id="u1") is None


class TestCallMcp:
    def test_success_logs_row(self, session_factory) -> None:
        reg, fake = _registry(session_factory)
        tools = reg.build_tool_map(user_id="u1")
        result = tools["mcp__fake__echo"](text="hi")
        assert result == "ok"
        assert fake.calls == [("echo", {"text": "hi"})]
        with session_factory() as db:
            items, total = list_calls(db)
        assert total == 1
        assert items[0]["tool_name"] == "mcp__fake__echo"
        assert items[0]["user_id"] == "u1"
        assert items[0]["status"] == "success"

    def test_failure_logs_error_row(self, session_factory) -> None:
        reg, _ = _registry(session_factory, FailingConn())
        tools = reg.build_tool_map(user_id="u1")
        result = tools["mcp__fake__echo"](text="hi")
        assert "error" in result
        with session_factory() as db:
            items, _ = list_calls(db)
        assert items[0]["status"] == "error"
        assert "boom" in (items[0]["error_message"] or "")

    def test_creates_s8_mcp_span(self, session_factory) -> None:
        reg, _ = _registry(session_factory)
        trace = PipelineTrace(scenario="chat", user_id="u1")
        token = set_trace(trace)
        try:
            reg.call_mcp("mcp__fake__echo", {"text": "hi"}, user_id="u1")
        finally:
            reset_trace(token)
        mcp_spans = [s for s in trace.spans if s.stage_name == "S8_mcp"]
        assert len(mcp_spans) == 1
        assert mcp_spans[0].metadata["endpoint_alias"] == "fake"
        assert mcp_spans[0].metadata["transport"] == "stdio"

    def test_log_write_failure_does_not_break_call(self) -> None:
        reg, fake = _registry(MagicMock())  # MagicMock session_factory
        reg._tracer = McpCallTracer(MagicMock())
        result = reg.call_mcp("mcp__fake__echo", {"text": "hi"}, user_id="u1")
        assert result == "ok"


class TestStatus:
    def test_status_and_tools_listing(self, session_factory) -> None:
        reg, _ = _registry(session_factory)
        status = reg.status()
        assert status[0]["alias"] == "fake"
        assert status[0]["state"] == "healthy"
        listing = reg.tools_listing()
        assert listing[0]["name"] == "mcp__fake__echo"
        assert listing[0]["source"] == "fake"
```

注：`test_log_write_failure_does_not_break_call` 中 `McpCallTracer(MagicMock())` 的 `with self._session_factory() as session` 会在 MagicMock 上成功但 `session.add(...)` 也是 MagicMock —— 为真正触发异常路径，改为传入一个调用即抛错的工厂：

```python
class _BrokenFactory:
    def __call__(self):
        raise RuntimeError("db down")
```

`reg._tracer = McpCallTracer(_BrokenFactory())`。

- [ ] **Step 4.4: 运行确认失败**

```bash
cd server; python -m pytest tests/unit/services/ai/test_tool_registry.py -v
```

Expected: FAIL（ModuleNotFoundError: app.services.ai.tool_registry）

- [ ] **Step 4.5: 实现 `server/app/services/ai/tool_registry.py`**

```python
"""Unified tool registry: built-in local tools + MCP remote tools.

Single source of truth for "what can the agent use". Local tools are rebuilt
per request (they bind ``user_id``); MCP connections are shared globally
(shared-process model) with per-call ``user_id`` logging.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.infrastructure.mcp_call_tracer import McpCallRecord, McpCallTracer
from app.services.ai.mcp_config import parse_endpoints, parse_stdios
from app.services.ai.mcp_connections import (
    McpCallError,
    McpLoop,
    McpTimeoutError,
    SseMcpConnection,
    StdioMcpConnection,
)
from app.services.ai.tool_factory import (
    ToolFn,
    build_tool_map,
    namespaced_tool_name,
    register_dynamic_specs,
)
from app.shared.pipeline_trace import get_trace, trace_span
from app.shared.tool_protocol import ToolSpec

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

SNAPSHOT_RESULT_CHARS = 512


@dataclass(frozen=True, slots=True)
class _McpToolEntry:
    alias: str
    raw_name: str
    spec: ToolSpec


class ToolRegistry:
    """Registry of all agent tools (local built-in + MCP remote)."""

    def __init__(self, container: ServiceContainer, settings: Any) -> None:
        self._container = container
        self._settings = settings
        self._loop = McpLoop()
        self._connections: dict[str, Any] = {}
        self._mcp_tools: dict[str, _McpToolEntry] = {}
        self._tracer: McpCallTracer | None = None

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None:
        self._loop.start()
        self._tracer = McpCallTracer(self._container.session_factory)
        for alias, url in parse_endpoints(self._settings.mcp_endpoints).items():
            self.register_connection(SseMcpConnection(alias, url, self._loop))
        for alias, spec in parse_stdios(self._settings.mcp_stdios).items():
            self.register_connection(StdioMcpConnection(alias, spec, self._loop))

    def register_connection(self, conn: Any) -> None:
        """Register + connect one MCP endpoint (best-effort, isolated)."""
        self._connections[conn.alias] = conn
        if not conn.connect():
            return
        self._sync_tools(conn)

    def close(self) -> None:
        for conn in self._connections.values():
            with contextlib.suppress(Exception):
                conn.close()
        self._loop.stop()

    # -- tool discovery ----------------------------------------------------

    def _sync_tools(self, conn: Any) -> None:
        # Drop stale entries of this alias before re-registering.
        for name in [n for n, e in self._mcp_tools.items() if e.alias == conn.alias]:
            del self._mcp_tools[name]
        try:
            tools = conn.list_tools()
        except Exception as exc:
            conn.state = "unhealthy"
            conn.last_error = str(exc)
            logger.warning("MCP list_tools %s failed: %s", conn.alias, exc)
            return
        conn.tool_count = len(tools)
        specs: dict[str, ToolSpec] = {}
        for tool in tools:
            full = namespaced_tool_name(conn.alias, tool.name)
            if full in self._mcp_tools:
                logger.warning("Duplicate MCP tool name %s skipped", full)
                continue
            schema = getattr(tool, "inputSchema", None) or {
                "type": "object",
                "properties": {},
            }
            spec = ToolSpec(
                name=full,
                description=getattr(tool, "description", "") or full,
                parameters=schema,
            )
            self._mcp_tools[full] = _McpToolEntry(conn.alias, tool.name, spec)
            specs[full] = spec
        register_dynamic_specs(specs)

    def _recover_unhealthy(self) -> None:
        """Lazy recovery: one reconnect attempt per unhealthy/dead endpoint."""
        for conn in self._connections.values():
            if conn.state == "healthy":
                continue
            if conn.connect():
                self._sync_tools(conn)

    # -- agent-facing API ---------------------------------------------------

    def build_tool_map(self, *, user_id: str = "default") -> dict[str, ToolFn] | None:
        """Per-request tool map: local tools (user-bound) + MCP tools."""
        self._recover_unhealthy()
        llm = self._container._llm_for_tier("light", agent_name="tool")
        retriever = self._container.retriever
        if llm is None or retriever is None:
            return None
        tools = build_tool_map(
            self._container.session_factory,
            retriever=retriever,
            llm=llm,
            user_id=user_id,
        )
        for name in self._mcp_tools:
            tools[name] = self._make_mcp_fn(name, user_id=user_id)
        return tools

    def _make_mcp_fn(self, name: str, *, user_id: str) -> ToolFn:
        def _call(**kwargs: Any) -> str:
            return self.call_mcp(name, kwargs, user_id=user_id)

        return _call

    def call_mcp(self, name: str, args: dict[str, Any], *, user_id: str) -> str:
        """One MCP tool call: S8_mcp span + mcp_call_logs row + error string."""
        entry = self._mcp_tools.get(name)
        if entry is None:
            return f"[{name}]: 未知工具"
        conn = self._connections[entry.alias]
        started = time.perf_counter()
        metadata: dict[str, Any] = {
            "endpoint_alias": entry.alias,
            "transport": conn.transport,
            "raw_tool_name": entry.raw_name,
            "restart_count": conn.restart_count,
        }
        result_text = ""
        error_message: str | None = None
        status = "success"
        with trace_span(
            "S8_mcp",
            f"MCP {entry.raw_name}",
            input_snapshot=dict(args),
            metadata=metadata,
        ) as span:
            try:
                result_text = conn.call_tool(entry.raw_name, args)
            except McpTimeoutError as exc:
                status = "timeout"
                error_message = str(exc)
                result_text = f"[{name} error]: {exc}"
            except McpCallError as exc:
                status = "error"
                error_message = str(exc)
                result_text = f"[{name} error]: {exc}"
            except Exception as exc:  # noqa: BLE001 — tool layer never raises
                status = "error"
                error_message = str(exc)
                result_text = f"[{name} error]: {exc}"
            if span:
                span.output_snapshot = result_text[:SNAPSHOT_RESULT_CHARS]
        self._record(
            user_id=user_id,
            entry=entry,
            transport=conn.transport,
            status=status,
            duration_ms=(time.perf_counter() - started) * 1000,
            error_message=error_message,
            args=args,
            result_text=result_text,
            span_id=span.span_id if span else "",
        )
        return result_text

    def _record(
        self,
        *,
        user_id: str,
        entry: _McpToolEntry,
        transport: str,
        status: str,
        duration_ms: float,
        error_message: str | None,
        args: dict[str, Any],
        result_text: str,
        span_id: str,
    ) -> None:
        if self._tracer is None:
            return
        trace = get_trace()
        self._tracer.record(
            McpCallRecord(
                user_id=user_id,
                trace_id=trace.trace_id if trace else None,
                span_id=span_id,
                endpoint_alias=entry.alias,
                transport=transport,
                tool_name=namespaced_tool_name(entry.alias, entry.raw_name),
                raw_tool_name=entry.raw_name,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
                arguments_snapshot=json.dumps(args, ensure_ascii=False, default=str),
                result_snapshot=result_text,
            )
        )

    # -- Dev API read models -------------------------------------------------

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "alias": conn.alias,
                "transport": conn.transport,
                "state": conn.state,
                "tool_count": conn.tool_count,
                "restart_count": conn.restart_count,
                "last_error": conn.last_error,
                "loaded_at": conn.loaded_at,
            }
            for conn in self._connections.values()
        ]

    def tools_listing(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": entry.spec.description,
                "source": entry.alias,
                "transport": self._connections[entry.alias].transport,
            }
            for name, entry in self._mcp_tools.items()
        ]
```

- [ ] **Step 4.6: 运行确认通过**

```bash
cd server; python -m pytest tests/unit/services/ai/test_tool_registry.py tests/unit/services/ai/test_tool_factory.py -v
```

Expected: PASS（registry 10 个用例 + tool_factory 原有用例不回归）

- [ ] **Step 4.7: 提交**

```bash
git add server/app/services/ai/tool_registry.py server/app/services/ai/tool_factory.py server/tests/unit/services/ai/test_tool_registry.py
git add server/tests/unit/services/ai/test_mcp_tool_factory.py
git commit -m "feat(ai): ToolRegistry 统一工具注册表 + 动态 spec；删除被取代的 build_tool_map_with_mcp"
```

（若 mcp_persistent.py 也删除了，一并 `git add` 对应删除文件）

---

### Task 5: Agent loop 集成

**Files:**
- Modify: `server/app/services/container.py`（+tool_registry 字段、+`ensure_tool_registry`、ensure_ai_stack 挂钩）
- Modify: `server/app/services/conversation_ai_service.py`（`_build_tools` 走注册表；两处 need_tools 过滤抽 `_filter_tools`）
- Modify: `server/app/services/ai/conversation_loop.py`（两处 enable_tools 放行 MCP）
- Modify: `server/app/services/ai/graph_nodes.py`（一处 enable_tools 放行 MCP）
- Modify: `server/app/main.py`（shutdown 关闭注册表）
- Test: `server/tests/unit/services/test_conversation_ai_service.py`（追加用例）

- [ ] **Step 5.1: 写失败测试（追加到现有文件）**

`server/tests/unit/services/test_conversation_ai_service.py` 追加：

```python
class TestBuildToolsWithRegistry:
    def test_build_tools_delegates_to_registry(self) -> None:
        from app.services import conversation_ai_service as svc

        container = MagicMock()
        registry = MagicMock()
        registry.build_tool_map.return_value = {"x": lambda **k: "ok"}
        container.__dict__["tool_registry"] = registry
        result = svc._build_tools(container, user_id="u1")
        registry.build_tool_map.assert_called_once_with(user_id="u1")
        assert result == {"x": registry.build_tool_map.return_value["x"]}

    def test_build_tools_falls_back_without_registry(self) -> None:
        from app.services import conversation_ai_service as svc

        container = MagicMock()
        container.retriever = None  # 无注册表 + 无 retriever → None（现行为）
        assert svc._build_tools(container, user_id="u1") is None


class TestFilterTools:
    def test_local_gated_mcp_always_available(self) -> None:
        from app.services.conversation_ai_service import _filter_tools

        all_tools = {
            "search_diary": lambda **k: "",
            "analyze_sentiment": lambda **k: "",
            "mcp__tavily__search": lambda **k: "",
        }
        result = _filter_tools(all_tools, ["search_diary"])
        assert set(result) == {"search_diary", "mcp__tavily__search"}

    def test_no_need_tools_mcp_only(self) -> None:
        from app.services.conversation_ai_service import _filter_tools

        all_tools = {"search_diary": lambda **k: "", "mcp__tavily__search": lambda **k: ""}
        result = _filter_tools(all_tools, [])
        assert set(result) == {"mcp__tavily__search"}

    def test_no_tools_at_all(self) -> None:
        from app.services.conversation_ai_service import _filter_tools

        assert _filter_tools(None, ["search_diary"]) is None
        assert _filter_tools({"search_diary": lambda **k: ""}, []) is None
```

- [ ] **Step 5.2: 运行确认失败**

```bash
cd server; python -m pytest tests/unit/services/test_conversation_ai_service.py -v
```

Expected: 新用例 FAIL（AttributeError: _filter_tools）

- [ ] **Step 5.3: 修改 conversation_ai_service.py**

(a) 导入区（`build_tool_map` 导入旁）加：

```python
from app.services.ai.tool_factory import is_mcp_tool
```

(b) `_build_tools`（约 327-340 行）替换为：

```python
def _build_tools(
    container: ServiceContainer, *, user_id: str = "default"
) -> dict[str, ToolFn] | None:
    """Build the tool map for the Agentic Loop, or None if unavailable."""
    try:
        # __dict__.get avoids auto-creating attributes on MagicMock containers
        # (same pattern as conversation_loop's graph lookup).
        registry = container.__dict__.get("tool_registry") if hasattr(container, "__dict__") else None
        if registry is not None:
            return registry.build_tool_map(user_id=user_id)
        llm = container._llm_for_tier("light", agent_name="tool")
        if llm is None or container.retriever is None:
            return None
        return build_tool_map(
            container.session_factory, retriever=container.retriever, llm=llm, user_id=user_id
        )
    except Exception as exc:
        logger.warning("Tool map build failed: %s", exc)
        return None


def _filter_tools(
    all_tools: dict[str, ToolFn] | None,
    need_tools: list[str],
) -> dict[str, ToolFn] | None:
    """Intent-gated local tools + always-available MCP tools."""
    if not all_tools:
        return None
    if need_tools:
        selected = {
            name: fn
            for name, fn in all_tools.items()
            if name in need_tools or is_mcp_tool(name)
        }
    else:
        selected = {name: fn for name, fn in all_tools.items() if is_mcp_tool(name)}
    return selected or None
```

(c) 两处过滤（约 652-654 行与 968-970 行，形如 `if all_tools and intent_result.need_tools: tools = {...}; if not tools: tools = None`）都替换为：

```python
tools = _filter_tools(all_tools, intent_result.need_tools)
```

- [ ] **Step 5.4: 修改 conversation_loop.py（两处 enable_tools）**

导入区加 `is_mcp_tool`（已有 `from app.services.ai.tool_factory import ToolFn, specs_for_names`，扩展为三元组导入）。

在 `_needs_tool_call`（约 138-144 行）之后加辅助函数：

```python
def _has_mcp_tools(tools: dict[str, ToolFn] | None) -> bool:
    """MCP tools bypass the intent whitelist — the LLM decides whether to call."""
    return any(is_mcp_tool(name) for name in (tools or {}))
```

约 398 行与 653 行的两处：

```python
enable_tools = tools is not None and len(tools) > 0 and len(intent_result.need_tools) > 0
```

替换为：

```python
enable_tools = (
    tools is not None
    and len(tools) > 0
    and (len(intent_result.need_tools) > 0 or _has_mcp_tools(tools))
)
```

- [ ] **Step 5.5: 修改 graph_nodes.py（约 90 行）**

```python
enable_tools = bool(tools) and len(intent_result.need_tools) > 0
```

替换为：

```python
enable_tools = bool(tools) and (
    len(intent_result.need_tools) > 0
    or any(is_mcp_tool(name) for name in tools)
)
```

并在导入区加 `from app.services.ai.tool_factory import is_mcp_tool`。

- [ ] **Step 5.6: 修改 container.py**

(a) 数据类字段区（`episodic_memory` 等字段旁，懒加载字段模式）加：

```python
    tool_registry: ToolRegistry | None = field(default=None, repr=False)
    _registry_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
```

（`ToolRegistry` 用 `if TYPE_CHECKING:` 导入避免循环导入；`threading` 若未导入则在文件头补 `import threading`；字段写法镜像现有 `_ai_lock` 的定义方式——实现时先看该文件里 `_ai_lock` 怎么声明就怎么写。）

(b) `ensure_memory`（约 181 行）之前加方法：

```python
    def ensure_tool_registry(self) -> ToolRegistry | None:
        """Create the ToolRegistry (local + MCP tools) once, lazily.

        Separate lock from ``_ai_lock`` so the Dev API can build the registry
        without loading the full AI stack. With no MCP endpoints configured
        this is nearly free.
        """
        if self.tool_registry is not None:
            return self.tool_registry
        with self._registry_lock:
            if self.tool_registry is None:
                from app.services.ai.tool_registry import ToolRegistry

                registry = ToolRegistry(self, self.settings)
                registry.initialize()
                self.tool_registry = registry
        return self.tool_registry
```

(c) `ensure_ai_stack`（约 194-230 行）末尾 `logger.info("AI stack ready ...")` 之前加：

```python
        self.ensure_tool_registry()
```

- [ ] **Step 5.7: 修改 main.py（shutdown 关闭注册表）**

`lifespan` 关闭段（约 185-186 行 `drain(timeout_s=5.0)` 之后）追加：

```python
    # Close MCP connections (stdio subprocesses) — best-effort.
    with suppress(Exception):
        container = app.state.container
        registry = getattr(container, "tool_registry", None)
        if registry is not None:
            await asyncio.to_thread(registry.close)
```

- [ ] **Step 5.8: 运行确认通过 + 全量后端回归**

```bash
cd server; python -m pytest tests/unit/services/test_conversation_ai_service.py tests/unit/services/ai/test_conversation_loop.py -v
python -m pytest -q
```

Expected: 新用例 PASS；全量回归无失败（现有 MagicMock 容器测试走 `__dict__.get` 返回 None → 原路径不变）

- [ ] **Step 5.9: 提交**

```bash
git add server/app/services/container.py server/app/services/conversation_ai_service.py server/app/services/ai/conversation_loop.py server/app/services/ai/graph_nodes.py server/app/main.py server/tests/unit/services/test_conversation_ai_service.py
git commit -m "feat(ai): agent loop 接入 ToolRegistry；MCP 工具绕过意图白名单；shutdown 清理连接"
```

---

### Task 6: Dev API 三端点

**Files:**
- Modify: `server/app/api/v1/dev.py`（路由区末尾追加）
- Test: `server/tests/unit/api/test_dev_mcp_api.py`

- [ ] **Step 6.1: 写失败测试**

`server/tests/unit/api/test_dev_mcp_api.py`：

```python
"""Unit tests for the MCP Dev API endpoints (status / tools / calls)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_mcp_status_empty(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/dev/mcp/status")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_mcp_tools_lists_local_tools(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/dev/mcp/tools")
    assert resp.status_code == 200
    items = resp.json()["items"]
    names = [t["name"] for t in items]
    assert "search_diary" in names
    assert "list_todos" in names
    assert all(t["source"] == "local" for t in items)


def test_mcp_calls_empty(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/dev/mcp/calls")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


def test_mcp_calls_pagination_params(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/dev/mcp/calls?page=1&page_size=5&status=success")
    assert resp.status_code == 200
    assert "total" in resp.json()
```

- [ ] **Step 6.2: 运行确认失败**

```bash
cd server; python -m pytest tests/unit/api/test_dev_mcp_api.py -v
```

Expected: FAIL（404）

- [ ] **Step 6.3: 实现 dev.py 三端点**

`server/app/api/v1/dev.py` 导入区补：

```python
from app.infrastructure.mcp_call_tracer import list_calls as list_mcp_calls
from app.services.ai.tool_factory import build_tool_specs
```

路由区（现有路由之后）追加：

```python
@router.get("/mcp/status")
def get_mcp_status(container: ContainerDep) -> dict[str, Any]:
    """MCP endpoint health: alias, transport, state, tool count, restarts."""
    registry = container.ensure_tool_registry()
    items = registry.status() if registry is not None else []
    return {"items": items}


@router.get("/mcp/tools")
def get_mcp_tools(container: ContainerDep) -> dict[str, Any]:
    """All agent tools: 8 local + MCP (source = 'local' | endpoint alias)."""
    registry = container.ensure_tool_registry()
    items = [
        {"name": s.name, "description": s.description, "source": "local", "transport": "local"}
        for s in build_tool_specs()
    ]
    if registry is not None:
        items.extend(registry.tools_listing())
    return {"items": items}


@router.get("/mcp/calls")
def list_mcp_call_logs(
    db: DbDep,
    endpoint: str | None = Query(None, description="Filter by endpoint alias"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    user: str | None = Query(None, description="Filter by user_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """MCP tool call log with filters and pagination."""
    items, total = list_mcp_calls(
        db,
        endpoint=endpoint,
        status=status_filter,
        user_id=user,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total}
```

- [ ] **Step 6.4: 运行确认通过**

```bash
cd server; python -m pytest tests/unit/api/test_dev_mcp_api.py tests/unit/api/test_dev_api.py -v
```

Expected: PASS（新 4 用例 + 原 dev API 用例不回归）

- [ ] **Step 6.5: 提交**

```bash
git add server/app/api/v1/dev.py server/tests/unit/api/test_dev_mcp_api.py
git commit -m "feat(dev): /dev/mcp/{status,tools,calls} 三个只读观测端点"
```

---

### Task 7: 全栈 e2e（真 stdio 子进程穿真实 API）

**Files:**
- Create: `server/tests/e2e/test_mcp_flow.py`

- [ ] **Step 7.1: 写 e2e 测试**

```python
"""E2E: MCP stdio server through the real Dev API (registry → API → log)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SCRIPT = Path(__file__).parents[1] / "fixtures" / "fake_mcp_stdio.py"


def _wait_ready(client: TestClient, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if client.get("/api/v1/dev/middleware-status").status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise TimeoutError("app bootstrap timed out")


@pytest.fixture()
def mcp_client(tmp_path):
    from app.config import Settings, get_settings
    from app.main import create_app

    settings = Settings(
        data_dir=str(tmp_path / "data"),
        llm_api_key="sk-test",
        llm_base_url="https://api.example.com/v1",
        llm_model="test-model",
        model_key_secret="test-model-secret-min-16-chars!!",
        database_url_env="",
        mcp_stdios=f"fake:{sys.executable} {SCRIPT}",
    )
    os.environ["DATA_DIR"] = settings.data_dir
    os.environ["DATABASE_URL"] = ""
    get_settings.cache_clear()
    app = create_app(settings)
    with TestClient(app) as client:
        _wait_ready(client)
        yield client
    get_settings.cache_clear()


def test_stdio_endpoint_visible_and_callable(mcp_client: TestClient) -> None:
    status = mcp_client.get("/api/v1/dev/mcp/status")
    assert status.status_code == 200
    items = status.json()["items"]
    assert len(items) == 1
    assert items[0]["alias"] == "fake"
    assert items[0]["state"] == "healthy"
    assert items[0]["tool_count"] == 2

    tools = mcp_client.get("/api/v1/dev/mcp/tools")
    names = [t["name"] for t in tools.json()["items"]]
    assert "mcp__fake__echo" in names
    assert "search_diary" in names  # 本地工具同列
```

- [ ] **Step 7.2: 运行确认通过**

```bash
cd server; python -m pytest tests/e2e/test_mcp_flow.py -v
```

Expected: PASS（真实 spawn `sys.executable fake_mcp_stdio.py`，Dev API 可见 healthy 端点与命名空间工具）

- [ ] **Step 7.3: 提交**

```bash
git add server/tests/e2e/test_mcp_flow.py
git commit -m "test(e2e): stdio MCP 端点全栈链路（真子进程 → 注册表 → Dev API）"
```

---

### Task 8: 前端（API 层 + McpPanel + DevScene 标签页）

**Files:**
- Modify: `src/shared/api/dev.ts`
- Create: `src/features/dev/McpPanel.vue`
- Modify: `src/pages/DevScene.vue`
- Test: `src/__tests__/McpPanel.spec.ts`

- [ ] **Step 8.1: dev.ts 加类型与 3 个函数（文件末尾追加）**

```ts
export interface McpEndpointStatus {
  alias: string
  transport: 'sse' | 'stdio'
  state: 'healthy' | 'unhealthy' | 'dead'
  tool_count: number
  restart_count: number
  last_error: string
  loaded_at: string
}

export interface McpToolInfo {
  name: string
  description: string
  source: string
  transport: string
}

export interface McpCallLog {
  id: string
  user_id: string | null
  trace_id: string | null
  endpoint_alias: string
  transport: string
  tool_name: string
  raw_tool_name: string
  status: string
  duration_ms: number
  error_message: string | null
  arguments_snapshot: string
  result_snapshot: string
  created_at: number
}

export async function getMcpStatus(): Promise<{ items: McpEndpointStatus[] }> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/mcp/status')
  return data
}

export async function getMcpTools(): Promise<{ items: McpToolInfo[] }> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/mcp/tools')
  return data
}

export async function listMcpCalls(params?: {
  endpoint?: string
  status?: string
  user?: string
  page?: number
  page_size?: number
}): Promise<{ items: McpCallLog[]; total: number }> {
  const client = await getHttpClient()
  const { data } = await client.get('/api/v1/dev/mcp/calls', { params })
  return data
}
```

- [ ] **Step 8.2: 写组件失败测试**

`src/__tests__/McpPanel.spec.ts`：

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/shared/api/dev', () => ({
  getMcpStatus: vi.fn(async () => ({
    items: [
      {
        alias: 'tavily',
        transport: 'stdio',
        state: 'healthy',
        tool_count: 3,
        restart_count: 1,
        last_error: '',
        loaded_at: '2026-09-04T10:00:00+00:00',
      },
    ],
  })),
  getMcpTools: vi.fn(async () => ({
    items: [
      { name: 'search_diary', description: '搜索历史日记', source: 'local', transport: 'local' },
      { name: 'mcp__tavily__search', description: '联网搜索', source: 'tavily', transport: 'stdio' },
    ],
  })),
  getMcpCalls: vi.fn(async () => ({
    items: [
      {
        id: 'c1',
        user_id: 'u1',
        trace_id: 't1',
        endpoint_alias: 'tavily',
        transport: 'stdio',
        tool_name: 'mcp__tavily__search',
        raw_tool_name: 'search',
        status: 'success',
        duration_ms: 1200,
        error_message: null,
        arguments_snapshot: '{"query": "上海 天气"}',
        result_snapshot: '{"results": []}',
        created_at: 1759970000,
      },
    ],
    total: 1,
  })),
}))

import { getMcpCalls, getMcpStatus, getMcpTools } from '@/shared/api/dev'
import McpPanel from '@/features/dev/McpPanel.vue'

function mountPanel() {
  return mount(McpPanel)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('McpPanel', () => {
  it('renders endpoint row with alias/transport/restart count', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('tavily')
    expect(text).toContain('stdio')
    expect(text).toContain('重启 1 次')
  })

  it('renders tool list with local and mcp source tags', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('mcp__tavily__search')
    expect(text).toContain('联网搜索')
    expect(text).toContain('search_diary')
  })

  it('expands a call row and emits openTrace on trace link click', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('.mcp-panel__row--button').trigger('click')
    expect(wrapper.text()).toContain('上海 天气')
    await wrapper.find('.mcp-panel__trace-link').trigger('click')
    expect(wrapper.emitted('openTrace')).toEqual([['t1']])
  })

  it('reloads all three sources on refresh click', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('.mcp-panel__refresh').trigger('click')
    await flushPromises()
    expect(getMcpStatus).toHaveBeenCalledTimes(2)
    expect(getMcpTools).toHaveBeenCalledTimes(2)
    expect(getMcpCalls).toHaveBeenCalledTimes(2)
  })

  it('shows empty endpoint hint when no endpoints configured', async () => {
    vi.mocked(getMcpStatus).mockResolvedValueOnce({ items: [] })
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('未配置 MCP 端点')
  })
})
```

- [ ] **Step 8.3: 运行确认失败**

```bash
npx vitest run src/__tests__/McpPanel.spec.ts
```

Expected: FAIL（无法解析 @/features/dev/McpPanel.vue）

- [ ] **Step 8.4: 实现 McpPanel.vue**

（细线列表风格：`--color-border` 1px 分隔、`--radius-inner` 8px、`--font-mono` 工具名，沿用 TraceList/TraceSpanRow 的视觉语言）

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { McpCallLog, McpEndpointStatus, McpToolInfo } from '@/shared/api/dev'
import { getMcpCalls, getMcpStatus, getMcpTools } from '@/shared/api/dev'

const emit = defineEmits<{ openTrace: [traceId: string] }>()

const endpoints = ref<McpEndpointStatus[]>([])
const tools = ref<McpToolInfo[]>([])
const calls = ref<McpCallLog[]>([])
const callsTotal = ref(0)
const loading = ref(false)
const statusFilter = ref('')
const expandedCallId = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    const [status, toolList, callList] = await Promise.all([
      getMcpStatus(),
      getMcpTools(),
      getMcpCalls(statusFilter.value ? { status: statusFilter.value } : undefined),
    ])
    endpoints.value = status.items
    tools.value = toolList.items
    calls.value = callList.items
    callsTotal.value = callList.total
  } catch {
    endpoints.value = []
    tools.value = []
    calls.value = []
    callsTotal.value = 0
  } finally {
    loading.value = false
  }
}

function toggleCall(id: string): void {
  expandedCallId.value = expandedCallId.value === id ? null : id
}

function stateLabel(state: string): string {
  if (state === 'healthy') return '正常'
  if (state === 'dead') return '已停止'
  return '异常'
}

function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

onMounted(() => void load())
</script>

<template>
  <div class="mcp-panel">
    <div class="mcp-panel__header">
      <span class="mcp-panel__title">MCP 工具</span>
      <button class="mcp-panel__refresh" :disabled="loading" @click="load">刷新</button>
    </div>

    <section class="mcp-panel__section">
      <h3 class="mcp-panel__section-title">端点（{{ endpoints.length }}）</h3>
      <div v-if="endpoints.length === 0" class="mcp-panel__empty">
        未配置 MCP 端点（.env 中设置 MCP_ENDPOINTS / MCP_STDIOS）
      </div>
      <template v-else>
        <div v-for="ep in endpoints" :key="ep.alias" class="mcp-panel__row">
          <span class="mcp-panel__dot" :class="`mcp-panel__dot--${ep.state}`" />
          <span class="mcp-panel__name">{{ ep.alias }}</span>
          <span class="mcp-panel__tag">{{ ep.transport }}</span>
          <span class="mcp-panel__meta">{{ ep.tool_count }} 工具</span>
          <span v-if="ep.transport === 'stdio'" class="mcp-panel__meta">重启 {{ ep.restart_count }} 次</span>
          <span class="mcp-panel__meta mcp-panel__meta--right">{{ stateLabel(ep.state) }}</span>
        </div>
        <div
          v-for="ep in endpoints.filter((e) => e.last_error)"
          :key="`err-${ep.alias}`"
          class="mcp-panel__row-error"
        >
          {{ ep.alias }}: {{ ep.last_error }}
        </div>
      </template>
    </section>

    <section class="mcp-panel__section">
      <h3 class="mcp-panel__section-title">工具清单（{{ tools.length }}）</h3>
      <div class="mcp-panel__rows">
        <div v-for="tool in tools" :key="tool.name" class="mcp-panel__row">
          <span class="mcp-panel__tool-name">{{ tool.name }}</span>
          <span class="mcp-panel__tag" :class="{ 'mcp-panel__tag--local': tool.source === 'local' }">
            {{ tool.source }}
          </span>
          <span class="mcp-panel__desc">{{ tool.description }}</span>
        </div>
      </div>
    </section>

    <section class="mcp-panel__section">
      <div class="mcp-panel__section-head">
        <h3 class="mcp-panel__section-title">调用流水（{{ callsTotal }}）</h3>
        <select v-model="statusFilter" class="mcp-panel__select" @change="load">
          <option value="">全部状态</option>
          <option value="success">success</option>
          <option value="error">error</option>
          <option value="timeout">timeout</option>
        </select>
      </div>
      <div v-if="calls.length === 0" class="mcp-panel__empty">暂无调用记录</div>
      <div v-else class="mcp-panel__rows">
        <template v-for="call in calls" :key="call.id">
          <button class="mcp-panel__row mcp-panel__row--button" @click="toggleCall(call.id)">
            <span
              class="mcp-panel__dot"
              :class="`mcp-panel__dot--${call.status === 'success' ? 'healthy' : 'error'}`"
            />
            <span class="mcp-panel__tool-name">{{ call.tool_name }}</span>
            <span class="mcp-panel__tag">{{ call.endpoint_alias }}</span>
            <span class="mcp-panel__meta">{{ formatDuration(call.duration_ms) }}</span>
            <span class="mcp-panel__meta">{{ call.status }}</span>
            <span class="mcp-panel__meta mcp-panel__meta--right">{{ formatTime(call.created_at) }}</span>
          </button>
          <div v-if="expandedCallId === call.id" class="mcp-panel__call-detail">
            <pre class="mcp-panel__code">{{ call.arguments_snapshot }}</pre>
            <pre class="mcp-panel__code">{{ call.result_snapshot }}</pre>
            <p v-if="call.error_message" class="mcp-panel__error">{{ call.error_message }}</p>
            <button
              v-if="call.trace_id"
              class="mcp-panel__trace-link"
              @click="emit('openTrace', call.trace_id)"
            >
              查看链路 →
            </button>
          </div>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.mcp-panel {
  height: 100%;
  overflow-y: auto;
  background: var(--color-bg);
}
.mcp-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--color-border);
}
.mcp-panel__title {
  font-family: var(--font-display);
  font-size: 1rem;
}
.mcp-panel__refresh {
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-button);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out-quart);
}
.mcp-panel__refresh:hover {
  background: var(--color-bg-elevated);
}
.mcp-panel__section {
  padding: 0.75rem 1rem 1rem;
}
.mcp-panel__section + .mcp-panel__section {
  border-top: 1px solid var(--color-border);
}
.mcp-panel__section-title {
  margin: 0 0 0.5rem;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}
.mcp-panel__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mcp-panel__select {
  padding: 0.125rem 0.375rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-button);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-size: 0.75rem;
}
.mcp-panel__rows {
  border-top: 1px solid var(--color-border);
}
.mcp-panel__row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.375rem 0.25rem;
  border: none;
  border-bottom: 1px solid var(--color-border);
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.75rem;
  color: var(--color-text-primary);
  text-align: left;
}
.mcp-panel__row--button {
  cursor: pointer;
}
.mcp-panel__row--button:hover {
  background: var(--color-bg-elevated);
}
.mcp-panel__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--color-danger);
  opacity: 0.5;
}
.mcp-panel__dot--healthy {
  background: var(--color-success);
  opacity: 1;
}
.mcp-panel__dot--error,
.mcp-panel__dot--dead {
  background: var(--color-danger);
  opacity: 1;
}
.mcp-panel__name {
  font-weight: 500;
}
.mcp-panel__tool-name {
  font-family: var(--font-mono);
  font-size: 0.7rem;
}
.mcp-panel__tag {
  padding: 0 0.375rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-seal);
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}
.mcp-panel__tag--local {
  color: var(--color-accent);
  border-color: var(--color-accent);
}
.mcp-panel__meta {
  color: var(--color-text-secondary);
  font-size: 0.6875rem;
}
.mcp-panel__meta--right {
  margin-left: auto;
}
.mcp-panel__desc {
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mcp-panel__row-error {
  padding: 0.375rem 0.25rem;
  border-bottom: 1px solid var(--color-border);
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--color-danger);
}
.mcp-panel__empty {
  padding: 0.75rem 0.25rem;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
}
.mcp-panel__call-detail {
  padding: 0.5rem 0.5rem 0.75rem 1rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
}
.mcp-panel__code {
  margin: 0 0 0.375rem;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-inner);
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-all;
}
.mcp-panel__error {
  margin: 0 0 0.375rem;
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--color-danger);
}
.mcp-panel__trace-link {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--color-accent);
  font-size: 0.75rem;
  cursor: pointer;
}
</style>
```

- [ ] **Step 8.5: DevScene.vue 加顶部标签切换**

(a) `<script setup>` 加（import 区 + 状态区）：

```ts
import McpPanel from '@/features/dev/McpPanel.vue'

const activeTab = ref<'traces' | 'mcp'>('traces')

function openTraceFromMcp(traceId: string) {
  activeTab.value = 'traces'
  void selectTrace(traceId)
}
```

(b) 模板整体结构改为（保留原有 TraceList/topbar/TraceWaterfall 内容不动，只是外面包了 tabs 与 body 两层）：

```vue
<template>
  <div class="dev-scene">
    <div class="dev-scene__tabs">
      <button
        class="dev-scene__tab"
        :class="{ 'dev-scene__tab--active': activeTab === 'traces' }"
        @click="activeTab = 'traces'"
      >
        链路追踪
      </button>
      <button
        class="dev-scene__tab"
        :class="{ 'dev-scene__tab--active': activeTab === 'mcp' }"
        @click="activeTab = 'mcp'"
      >
        MCP
      </button>
    </div>
    <div v-if="activeTab === 'mcp'" class="dev-scene__mcp">
      <McpPanel @open-trace="openTraceFromMcp" />
    </div>
    <div v-else class="dev-scene__body">
      <!-- 原 sidebar + main 原样移入 -->
      <div class="dev-scene__sidebar">
        <TraceList :traces="traces" :total="total" :loading="loading" @select="selectTrace" />
      </div>
      <div class="dev-scene__main">
        <!-- 原 topbar + TraceWaterfall/empty 原样移入 -->
      </div>
    </div>
  </div>
</template>
```

(c) 样式调整（`.dev-scene` 从 grid 改为纵向 flex，原 grid 规则移到 `.dev-scene__body`）：

```css
.dev-scene {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 5rem);
  overflow: hidden;
}
.dev-scene__tabs {
  display: flex;
  gap: 0.25rem;
  padding: 0.375rem 1rem 0;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
}
.dev-scene__tab {
  padding: 0.375rem 0.875rem;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}
.dev-scene__tab--active {
  color: var(--color-text-primary);
  border-bottom-color: var(--color-accent);
}
.dev-scene__body {
  display: grid;
  grid-template-columns: 18rem 1fr;
  flex: 1;
  overflow: hidden;
}
.dev-scene__mcp {
  flex: 1;
  overflow: hidden;
}
```

（原 `.dev-scene` 的 `grid-template-columns: 18rem 1fr` 规则删除；`.dev-scene__sidebar` / `.dev-scene__main` / topbar / empty 规则原样保留。）

- [ ] **Step 8.6: 运行确认通过 + 前端全量**

```bash
npx vitest run src/__tests__/McpPanel.spec.ts
npx vitest run
npx vue-tsc --noEmit
npx eslint src --ext .ts,.vue
```

Expected: McpPanel 5 用例 PASS；全量 vitest 无回归；类型与 lint 零警告

- [ ] **Step 8.7: 提交**

```bash
git add src/shared/api/dev.ts src/features/dev/McpPanel.vue src/pages/DevScene.vue src/__tests__/McpPanel.spec.ts
git commit -m "feat(dev): Dev 面板 MCP 标签页（端点健康/工具清单/调用流水→trace 跳转）"
```

---

### Task 9: 部署配置与文档

**Files:**
- Modify: `docker-compose.yml`
- Modify: `server/.env.example`

- [ ] **Step 9.1: docker-compose.yml 加 mcp profile 与 env 透传**

(a) `backend` 服务 `environment:` 列表（`NEO4J_PASSWORD` 行之后）追加两行：

```yaml
      - MCP_ENDPOINTS=${MCP_ENDPOINTS:-}
      - MCP_STDIOS=${MCP_STDIOS:-}
```

(b) 文件末尾 `volumes:` 之前追加两个可选服务（stdio server 经 supergateway 桥接为 SSE，供容器网络内访问）：

```yaml
  # ── 可选 MCP 工具服务（docker compose --profile mcp up -d 启用）──────
  # stdio MCP server 经 supergateway 桥接为 SSE。启用后在根目录 .env 配置：
  #   MCP_ENDPOINTS=fetch:http://mcp-fetch:9201/sse,tavily:http://mcp-tavily:9202/sse
  mcp-fetch:
    image: node:20-alpine
    command: npx -y supergateway --stdio "npx -y @modelcontextprotocol/server-fetch" --port 9201
    ports:
      - "9201:9201"
    profiles: [mcp]
    restart: unless-stopped

  mcp-tavily:
    image: node:20-alpine
    command: npx -y supergateway --stdio "npx -y tavily-mcp" --port 9202
    environment:
      - TAVILY_API_KEY=${TAVILY_API_KEY:-}
    ports:
      - "9202:9202"
    profiles: [mcp]
    restart: unless-stopped
```

- [ ] **Step 9.2: server/.env.example 追加**

```bash
# ── MCP 工具（可选）────────────────────────────────────────────
# SSE 端点。格式: 别名:URL,别名:URL。docker compose --profile mcp 部署时用服务名：
# MCP_ENDPOINTS=fetch:http://mcp-fetch:9201/sse,tavily:http://mcp-tavily:9202/sse
MCP_ENDPOINTS=
# stdio 子进程。格式: 别名:命令 参数 环境键=值（不支持带空格的路径）：
# MCP_STDIOS=tavily:uvx tavily-mcp api_key=xxx
MCP_STDIOS=
```

- [ ] **Step 9.3: 提交**

```bash
git add docker-compose.yml server/.env.example
git commit -m "chore(deploy): docker-compose mcp profile 与 MCP 配置透传"
```

---

### Task 10: 全量回归 + PR

- [ ] **Step 10.1: 后端全量**

```bash
cd server
python -m pytest -q
python -m ruff check .
python -m mypy .
```

Expected: pytest 全绿（约 1000+ 用例）；ruff 零告警；mypy 零错误

- [ ] **Step 10.2: 前端全量**

```bash
npx vitest run
npx vue-tsc --noEmit
npx eslint src --ext .ts,.vue
```

Expected: 全绿零警告

- [ ] **Step 10.3: 本地手动验收（可选但推荐，Docker）**

```bash
docker compose build backend frontend
docker compose up -d
docker compose --profile mcp up -d
```

验收清单（对应 spec 7.4）：面板 MCP 标签页端点全绿、工具清单含 `mcp__fetch__fetch`；笔谈提问触发工具后调用流水有记录；`docker kill` 某 mcp 容器后面板变灰、信件降级正常；链路图出现 S8_mcp span；`mcp_call_logs` 有数据。

- [ ] **Step 10.4: 推送并开 PR**

```bash
git push -u origin feat/mcp-tool-registry-pr12
```

PR 标题：`feat: MCP 工具注册表——统一工具入口与开发者可观测性（PR12）`

PR 描述模板：

```markdown
## 标题
MCP 工具注册表（ToolRegistry）：本地工具 + MCP SSE/stdio 远程工具统一入口，配套 mcp_call_logs 持久化、Dev API /dev/mcp/* 三端点、前端 MCP 标签页与 S8_mcp trace 嵌入。

## 功能描述
- ToolRegistry 统一工具入口：本地 8 工具（按 user_id 每请求重建）+ MCP 远程工具（`mcp__{alias}__{tool}` 命名空间，全局共享连接）
- MCP 连接层：共享后台事件循环（McpLoop），SSE/stdio 双传输，指数退避重启（1s→2s→4s），超时 30s，lazy 恢复
- MCP 工具绕过意图白名单（need_tools）：本地工具仍按意图门控，MCP 工具由 LLM 自主决定调用
- mcp_call_logs 表（快照截断 2KB，best-effort 落库）+ alembic 010
- Dev API：GET /dev/mcp/{status,tools,calls}
- 前端 Dev 面板新增 MCP 标签页：端点健康（state/重启次数）、工具清单（local/别名来源徽标）、调用流水（展开快照、trace_id 跳回链路图）
- S8_mcp span 嵌入现有 trace（元数据含 transport/endpoint/restart_count）
- docker-compose mcp profile（supergateway 桥接）+ MCP_ENDPOINTS/MCP_STDIOS 配置
- 删除被取代的 build_tool_map_with_mcp / _load_mcp_tools（从未接入业务路径）

## 实现思路
（按 spec：docs/superpowers/specs/2026-09-04-mcp-tool-registry-pr12.md 方案二；偏差三点——pid 不可得改 state/restart_count、need_tools 白名单放行 MCP、旧 MCP 代码删除——见 plan 头部）

## 测试方式
- pytest 全量 N 通过：mcp_config 解析 10、连接层 8（真子进程：spawn 失败/崩溃重启/超时/关闭）、tracer 7、registry 10（命名空间/合并/调用落库/span/best-effort）、Dev API 4、e2e 1（真 stdio 穿真实 API）
- vitest 全量 N 通过：McpPanel 5（端点渲染/工具清单/展开+trace 跳转/刷新/空态）
- ruff / mypy / vue-tsc / eslint 全绿；CI 全绿
```

（N 由实际运行数填充；无 Co-Authored-By 尾注。）

---

## Self-Review 结论

**Spec 覆盖核对**（spec 章节 → 任务）：
- §4.2 ToolRegistry → Task 4；§4.3 连接层双形态/退避重启/超时/共享进程 → Task 2；§4.4 agent loop 平滑迁移 → Task 5
- §5.1 配置格式/env 注入不进快照 → Task 1 + Task 4（arguments_snapshot 只含调用参数，env 只注入子进程）；§5.2 命名空间/撞名拒绝 → Task 4（`_sync_tools` 重复检查 + warning）；§5.3 零回归 → Task 5 Step 5.8 全量回归 + 未配置时 registry 只含本地工具（`_mcp_tools` 空）
- §6.1 mcp_call_logs → Task 3；§6.2 Dev API → Task 6；§6.3 面板 → Task 8；§6.4 S8_mcp span → Task 4（call_mcp 内 trace_span）+ 前端零改动（TraceSpanRow 已渲染 metadata/输入/输出）
- §7.1 单测 → Task 1/2/3/4；§7.2 e2e → Task 7（真 stdio 子进程穿真实 API，等价覆盖 spec 的 SSE e2e——SSE 传输由 Task 2 mock 单测覆盖 + 手动验收）；§7.3 前端 vitest → Task 8；§7.4 手动验收 → Task 10.3
- §8 DoD → Task 10；§9 单 PR → Task 0-10 同分支 8 个提交
- §10 风险对策：Windows stdio（Task 2 用 sys.executable 直 spawn 测试 + SDK 管理进程）、agent loop 回归（Task 5.8）、schema 不兼容（Task 4 `_sync_tools` 的 `inputSchema or 默认 object` 兜底）、日志膨胀（Task 3 截断 2KB）

**类型一致性核对**：`McpConnection.connect()->bool` / `list_tools()->list[Any]` / `call_tool(name, args)->str` / `close()` 在 Task 2 定义、Task 4（registry）与测试 FakeConn 签名一致；`McpCallRecord` 字段与 `McpCallLogRow` 列一一对应；`register_connection(conn)` Task 4 定义、Task 4 测试使用；前端 `McpEndpointStatus.state` 的三值与后端 `conn.state` 一致；`is_mcp_tool`/`namespaced_tool_name` 定义于 tool_factory（Task 4 Step 4.1），被 registry/conversation_ai_service/conversation_loop/graph_nodes 引用一致。

**占位符扫描**：Task 5 Step 5.3(c) 的"两处过滤替换"与 Step 5.6(a) 的"镜像 _ai_lock 写法"指向具体行号与完整新代码，属定位性说明而非占位；其余步骤均含完整代码。
