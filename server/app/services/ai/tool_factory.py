"""Tool factory functions for the ReAct agent executor (single-user)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.infrastructure.models.app_config import AppConfigRow
from app.services.ai.utils import filter_diary_results, format_diary_result
from app.shared.llm import LLMClient, message_text

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
                    "date": hit.metadata.get("date", ""),
                    "tags": hit.metadata.get("tags", ""),
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


def create_weather_tool(db: Session, *, weather_api_key: str = "") -> ToolFn:
    def get_weather_info() -> str:
        address = _get_config_value(db, "user_address")
        if not address:
            return "未设置地址。"
        api_key = weather_api_key or _get_config_value(db, "weather_api_key")
        result = _fetch_weather_from_api(address, api_key)
        return result or "天气获取失败"

    return get_weather_info


def create_address_tool(db: Session) -> ToolFn:
    def get_user_address() -> str:
        address = _get_config_value(db, "user_address")
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


def build_tool_map(
    db: Session,
    *,
    retriever: Any,
    llm: LLMClient,
    weather_api_key: str = "",
) -> dict[str, ToolFn]:
    return {
        "search_diary": create_diary_search_tool(retriever),
        "get_weather_info": create_weather_tool(db, weather_api_key=weather_api_key),
        "get_user_address": create_address_tool(db),
        "analyze_sentiment": create_sentiment_tool(llm),
    }
