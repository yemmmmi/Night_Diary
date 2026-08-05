"""统一工具协议——桥接原生函数调用与文本标签协议。

两条路径：
1. 原生：如果 LLM 客户端暴露 ``bind_tools``，则用 ToolSpec 模式调用它，
   并从响应中解析 ``tool_calls``。
2. 回退：在提示词中注入文本标签提示，并从响应文本中解析
   ``<tool>name</tool><args>{...}</args>``。

调用方（ConversationLoop / AgentExecutor）使用 ``invoke_with_tools``，
它会自动检测路径。这使得循环逻辑与协议无关。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

#: 文本标签回退模式（共享的单一真相来源）。
TOOL_CALL_PATTERN = re.compile(r"<tool>(\w+)</tool>\s*<args>(.*?)</args>", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """工具的模式描述，用于原生函数调用。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCallResult:
    """从任一协议路径解析出的工具调用。"""

    name: str
    args: dict[str, Any]


def parse_text_tag_calls(text: str) -> list[ToolCallResult]:
    """从文本中解析 ``<tool>name</tool><args>json</args>``（回退路径）。"""
    results: list[ToolCallResult] = []
    for match in TOOL_CALL_PATTERN.finditer(text):
        name = match.group(1)
        raw_args = match.group(2).strip()
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {"query": raw_args}
        results.append(ToolCallResult(name=name, args=args))
    return results


def strip_tool_tags(text: str) -> str:
    """从最终响应文本中移除工具调用标签。"""
    return TOOL_CALL_PATTERN.sub("", text).strip()


def build_tool_hint(tool_specs: list[ToolSpec]) -> str:
    """构建追加到提示词的文本标签提示（回退路径）。"""
    lines = [
        '\n\n如需调用工具查询信息，请输出：<tool>工具名</tool> <args>{"参数": "值"}</args>',
        "可用工具：",
    ]
    for spec in tool_specs:
        lines.append(f"- {spec.name}（{spec.description}）")
    lines.append("仅当确需查询信息时才调用工具。")
    return "\n".join(lines)


def supports_native_tools(llm: Any) -> bool:
    """检测 LLM 客户端是否支持原生函数调用。"""
    return hasattr(llm, "bind_tools") and callable(llm.bind_tools)


def extract_native_tool_calls(response: Any) -> list[ToolCallResult]:
    """从 LangChain AIMessage 中提取 tool_calls（原生路径）。

    同时处理字典和对象格式，以兼容不同版本的 LangChain。
    """
    results: list[ToolCallResult] = []
    tool_calls = getattr(response, "tool_calls", None) or []
    for tc in tool_calls:
        if isinstance(tc, dict):
            name = tc.get("name", "")
            args = tc.get("args", {})
        else:
            name = getattr(tc, "name", "")
            args = getattr(tc, "args", {})
        if name:
            results.append(ToolCallResult(name=name, args=dict(args)))
    return results


__all__ = [
    "TOOL_CALL_PATTERN",
    "ToolCallResult",
    "ToolSpec",
    "build_tool_hint",
    "extract_native_tool_calls",
    "parse_text_tag_calls",
    "strip_tool_tags",
    "supports_native_tools",
]
