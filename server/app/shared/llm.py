"""用于 AI 管道依赖注入的最小 LLM 客户端端口。

这是领域层依赖的唯一 LLM *端口*。智能体（B-8）通过构造函数接收满足
:class:`LLMClient` 的对象，并且永远不会自行构造 LLM（智能体内部不出现
``ChatOpenAI()`` / ``os.getenv``）。

有意声明了两个方法：

* ``invoke``——同步；由评估 :class:`~tests.eval.judge.LLMJudge` 和同步调用方
  （例如 ``SentimentSkill``）使用。
* ``ainvoke``——异步；由 Worker 智能体使用，它们在 B-9 的 ``asyncio.gather``
  扇出下并发运行。

两者都返回 ``Any``，因为响应是*类消息*对象：调用方通过
``getattr(response, "content", response)`` 读取文本，并通过
:func:`app.domain.agents.state.extract_token_usage` 提取 token 使用量（它读取
``response.response_metadata``）。因此，单纯的 ``str`` 也满足内容提取路径
（使用量降级为零）。

具体实现——一个根据按层级的 :class:`~app.shared.llm_factory.LLMFactory` 配置
组装的 LangChain ``BaseChatModel``——位于 ``llm_factory.py`` 中。此 Protocol
使领域代码与 ``langchain-openai`` 解耦：单元测试注入桩，离线评估注入一个
轻量的 HTTP 适配器。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """用于通过依赖注入使用的 LLM 聊天模型结构化端口。"""

    def invoke(self, prompt: str) -> Any:
        """同步完成 ``prompt`` 并返回类消息结果。"""
        ...

    async def ainvoke(self, prompt: str) -> Any:
        """异步完成 ``prompt`` 并返回类消息结果。"""
        ...


@runtime_checkable
class ToolCapableLLMClient(Protocol):
    """额外支持原生函数调用的 LLM 客户端。

    实现（例如 ChatOpenAI）暴露 ``bind_tools``，返回一个接受工具规范并产生
    带 ``tool_calls`` 响应的可运行对象。TracingLLMClient 透明地委托此调用。
    """

    def invoke(self, prompt: str) -> Any: ...

    async def ainvoke(self, prompt: str) -> Any: ...

    def bind_tools(self, tools: list[Any]) -> Any: ...


def message_text(response: Any) -> str:
    """从类消息的 LLM 响应中提取文本正文。

    接受 LangChain ``AIMessage``（``.content``）或纯 ``str``，因此同一个调用点
    既适用于生产模型，也适用于桩回复。
    """
    content = getattr(response, "content", response)
    return str(content)


__all__ = ["LLMClient", "ToolCapableLLMClient", "message_text"]
