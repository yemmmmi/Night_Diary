"""软覆盖（P2-B）条目的召回策略。

已退役条目在装载期就被过滤掉了：``EpisodicMemory.load()`` 用默认参数读
存储，进程内 deque 从来不含它们。因此历史召回必须由调用点显式开启，
而不是给 deque 加一个查询期开关。

召回旧观点只在"用户明确回看自己的过去"时才是证据而非噪声；其余语境
（尤其危机）必须让旧观点留在场外——那正是软覆盖机制本身要防的事故。
"""

from __future__ import annotations

#: 会正当地询问用户自身历史的意图——此时被修正前的旧观点是证据。
RETROSPECTIVE_INTENTS: frozenset[str] = frozenset(
    {"retrospective_query", "retrospective_review"}
)

#: 历史节每轮最多占用的条目数。防止历史挤掉当下事实占用的主检索槽位。
HISTORY_SECTION_MAX = 2


def allow_superseded_recall(
    intent_category: str | None,
    *,
    crisis_detected: bool,
) -> bool:
    """本轮是否可召回已被软覆盖的条目。

    ``crisis_detected`` 是硬红线而非同级信号：任何意图都不能覆盖它，因为在
    危机语境使用过期观点，恰恰是软覆盖机制要防的伤害。该参数被设计为必填
    （而不是默认 False），这样每个调用点都必须显式声明危机状态。
    """
    if crisis_detected:
        return False
    return intent_category in RETROSPECTIVE_INTENTS
