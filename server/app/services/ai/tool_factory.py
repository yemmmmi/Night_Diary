"""Tool factory functions for the ReAct agent executor (single-user)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models.app_config import AppConfigRow
from app.services.ai.utils import filter_diary_results, format_diary_result
from app.shared.llm import LLMClient, message_text
from app.shared.tool_protocol import ToolSpec

logger = logging.getLogger(__name__)

ToolFn = Callable[..., str]


def _get_config_value(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppConfigRow).filter(AppConfigRow.key == key).first()
    return row.value if row and row.value else default


def create_diary_search_tool(
    retriever: Any,
) -> ToolFn:
    def search_diary(
        query: str = "",
        start_date: str = "",
        end_date: str = "",
        tag: str = "",
    ) -> str:
        try:
            hits = retriever.retrieve(query or "", top_k=10)
            results = [
                {
                    "date": hit.date,
                    "tags": hit.tags,
                    "content": hit.content,
                }
                for hit in hits
            ]
            results = filter_diary_results(
                results,
                start_date=start_date,
                end_date=end_date,
                tag=tag,
            )[:5]
            if not results:
                return "未找到匹配的历史日记。"
            return "\n".join(format_diary_result(item) for item in results)
        except Exception as exc:
            logger.error("日记搜索工具失败: %s", exc)
            return "日记搜索暂时不可用"

    return search_diary


def _fetch_weather_from_api(city: str, api_key: str) -> str | None:
    if not api_key:
        return None
    try:
        with httpx.Client(timeout=5.0) as client:
            geo_resp = client.get(
                "https://restapi.amap.com/v3/geocode/geo",
                params={"address": city, "key": api_key, "output": "JSON"},
            )
            geo_data = geo_resp.json()
            if geo_data.get("status") != "1" or not geo_data.get("geocodes"):
                return None
            adcode = geo_data["geocodes"][0].get("adcode")
            w_resp = client.get(
                "https://restapi.amap.com/v3/weather/weatherInfo",
                params={
                    "city": adcode,
                    "key": api_key,
                    "extensions": "base",
                    "output": "JSON",
                },
            )
            w_data = w_resp.json()
            if w_data.get("status") != "1" or not w_data.get("lives"):
                return None
            live = w_data["lives"][0]
            return (
                f"{live.get('weather', '未知')} {live.get('temperature', '--')}°C "
                f"湿度{live.get('humidity', '--')}%"
            )
    except Exception as exc:
        logger.error("天气 API 失败: %s", exc)
        return None


def create_weather_tool(
    session_factory: sessionmaker[Session], *, weather_api_key: str = ""
) -> ToolFn:
    def get_weather_info() -> str:
        with session_factory() as session:
            address = _get_config_value(session, "user_address")
            api_key = weather_api_key or _get_config_value(session, "weather_api_key")
        # session closed — connection released before the network call
        if not address:
            return "未设置地址。"
        result = _fetch_weather_from_api(address, api_key)
        return result or "天气获取失败"

    return get_weather_info


def create_address_tool(session_factory: sessionmaker[Session]) -> ToolFn:
    def get_user_address() -> str:
        with session_factory() as session:
            address = _get_config_value(session, "user_address")
        return address or "用户未设置地址信息"

    return get_user_address


def create_sentiment_tool(llm: LLMClient) -> ToolFn:
    def analyze_sentiment(text: str) -> str:
        if not text or not text.strip():
            return "无法分析空内容"
        prompt = f"""请对以下文本进行情感分析，严格按照以下格式输出：
情感倾向：[正面/负面/中性]
情感强度：[1-5]
关键情感词：[词1, 词2, ...]

文本：{text}"""
        try:
            return message_text(llm.invoke(prompt))
        except Exception as exc:
            logger.error("情感分析工具失败: %s", exc)
            return "情感分析暂时不可用"

    return analyze_sentiment


def create_entity_graph_tool(user_id: str = "default") -> ToolFn:
    """Create a tool that queries the Neo4j entity graph for related entities."""

    def query_entity_graph(
        entity_name: str = "",
        emotion: str = "",
        max_depth: int = 2,
    ) -> str:
        from app.infrastructure.entity_graph import (
            is_neo4j_available,
            query_entities_by_emotion,
            query_related_entities,
        )

        if not is_neo4j_available():
            return "实体图不可用（未配置 Neo4j）"

        try:
            if emotion and not entity_name:
                results = query_entities_by_emotion(user_id, emotion, limit=10)
                if not results:
                    return f"未找到与情绪「{emotion}」相关的实体"
                lines = [f"情绪「{emotion}」相关实体："]
                for r in results:
                    lines.append(f"- {r['name']}（{r['type']}）被提及 {r['mention_count']} 次")
                return "\n".join(lines)

            if entity_name:
                results = query_related_entities(
                    user_id, entity_name, max_depth=max_depth, limit=10
                )
                if not results:
                    return f"未找到与「{entity_name}」相关的实体"
                lines = [f"与「{entity_name}」相关的实体："]
                for r in results:
                    rels = "→".join(r.get("relation_types", []))
                    lines.append(f"- {r['name']}（{r['type']}）关系:{rels} 深度:{r['depth']}")
                return "\n".join(lines)

            return "请提供 entity_name 或 emotion 参数"
        except Exception as exc:
            logger.error("实体图查询失败: %s", exc)
            return "实体图查询暂时不可用"

    return query_entity_graph


def build_tool_map(
    session_factory: sessionmaker[Session],
    *,
    retriever: Any,
    llm: LLMClient,
    weather_api_key: str = "",
    user_id: str = "default",
) -> dict[str, ToolFn]:
    return {
        "search_diary": create_diary_search_tool(retriever),
        "get_weather_info": create_weather_tool(session_factory, weather_api_key=weather_api_key),
        "get_user_address": create_address_tool(session_factory),
        "analyze_sentiment": create_sentiment_tool(llm),
        "query_entity_graph": create_entity_graph_tool(user_id=user_id),
    }


def build_tool_specs() -> list[ToolSpec]:
    """Return ToolSpec schemas for all built-in tools (for native function calling)."""
    return [
        ToolSpec(
            name="search_diary",
            description="搜索历史日记，支持关键词/日期/标签多维度查询",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                    "tag": {"type": "string", "description": "标签过滤"},
                },
                "required": ["query"],
            },
        ),
        ToolSpec(
            name="get_weather_info",
            description="查询用户地址的当前天气",
            parameters={"type": "object", "properties": {}},
        ),
        ToolSpec(
            name="get_user_address",
            description="获取用户设置的地址信息",
            parameters={"type": "object", "properties": {}},
        ),
        ToolSpec(
            name="analyze_sentiment",
            description="分析文本的情感倾向、强度和关键情感词",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "待分析文本"},
                },
                "required": ["text"],
            },
        ),
        ToolSpec(
            name="query_entity_graph",
            description="查询实体图中人物/实体的关系和情感关联",
            parameters={
                "type": "object",
                "properties": {
                    "entity_name": {"type": "string", "description": '实体名称（如"妈妈"）'},
                    "emotion": {"type": "string", "description": '情绪标签（如"低落"）'},
                    "max_depth": {"type": "integer", "description": "关系查询深度，默认2"},
                },
            },
        ),
    ]


def specs_for_names(names: list[str]) -> list[ToolSpec]:
    """Filter ToolSpec list to only the named tools (for intent-driven subset)."""
    all_specs = {s.name: s for s in build_tool_specs()}
    return [all_specs[n] for n in names if n in all_specs]


def _load_mcp_tools(endpoint: str) -> dict[str, ToolFn]:
    """Load tools from an external MCP server endpoint.

    Uses the MCP client protocol to discover tools and wraps them as ToolFn
    callables. Best-effort: returns empty dict on failure.

    Args:
        endpoint: MCP server SSE endpoint URL (e.g. http://localhost:8081/sse).
    """
    try:
        import asyncio

        from mcp import ClientSession
        from mcp.client.sse import sse_client
    except ImportError:
        logger.warning("mcp package not installed; cannot load MCP tools from %s", endpoint)
        return {}

    async def _discover_and_create() -> dict[str, ToolFn]:
        tools: dict[str, ToolFn] = {}
        try:
            async with sse_client(endpoint) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()

                for mcp_tool in result.tools:
                    # Capture tool name in closure
                    tool_name = mcp_tool.name

                    def make_fn(name: str) -> Any:
                        async def _call_async(**kwargs: Any) -> str:
                            resp = await session.call_tool(name, kwargs)
                            # Extract text from response content
                            texts = [c.text for c in resp.content if hasattr(c, "text")]
                            return "\n".join(texts) if texts else str(resp)

                        def _call_sync(**kwargs: Any) -> str:
                            try:
                                return asyncio.run(_call_async(**kwargs))
                            except Exception as exc:
                                logger.error("MCP tool %s failed: %s", name, exc)
                                return f"MCP tool {name} error: {exc}"

                        return _call_sync

                    tools[tool_name] = make_fn(tool_name)
                    logger.info("Loaded MCP tool: %s from %s", tool_name, endpoint)

        except Exception as exc:
            logger.error("Failed to load MCP tools from %s: %s", endpoint, exc)

        return tools

    try:
        return asyncio.run(_discover_and_create())
    except Exception as exc:
        logger.error("MCP discovery failed for %s: %s", endpoint, exc)
        return {}


def build_tool_map_with_mcp(
    session_factory: sessionmaker[Session],
    *,
    retriever: Any,
    llm: LLMClient,
    weather_api_key: str = "",
    user_id: str = "default",
    mcp_endpoints: list[str] | None = None,
) -> dict[str, ToolFn]:
    """Build tool map with optional external MCP tools.

    Combines built-in tools (from build_tool_map) with external tools loaded
    from MCP server endpoints. MCP tools are loaded best-effort — failures
    are logged and don't block the built-in tools.

    Args:
        mcp_endpoints: List of MCP server SSE endpoint URLs. If None or empty,
            only built-in tools are returned.

    Returns:
        Combined tool map (built-in + MCP).
    """
    # Start with built-in tools
    tools = build_tool_map(
        session_factory,
        retriever=retriever,
        llm=llm,
        weather_api_key=weather_api_key,
        user_id=user_id,
    )

    # Load external MCP tools
    if mcp_endpoints:
        for endpoint in mcp_endpoints:
            endpoint = endpoint.strip()
            if not endpoint:
                continue
            logger.info("Loading MCP tools from endpoint: %s", endpoint)
            mcp_tools = _load_mcp_tools(endpoint)
            if mcp_tools:
                tools.update(mcp_tools)
                logger.info(
                    "MCP tools loaded from %s: %s",
                    endpoint,
                    list(mcp_tools.keys()),
                )

    return tools
