"""User-intent routing for the record / insight / plan skills (PR8).

Two-stage routing keeps plain-chat latency at zero:

1. **Strong rules** — high-confidence instruction patterns (e.g. "帮我记一
   篇日记") route directly without any LLM call.
2. **Weak-signal gate + light LLM fallback** — only when the message carries
   a skill affordance ("帮我", "我想", "为什么"…) do we spend one light-LLM
   four-way classification; everything else stays on the normal chat path.

Any failure or ambiguity degrades to ``"chat"`` — the skill layer is strictly
additive and never blocks a normal reply.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.shared.llm import LLMClient, message_text

logger = logging.getLogger(__name__)

USER_INTENTS = ("record", "insight", "plan", "chat")

RECORD_STRONG: tuple[str, ...] = (
    "帮我记一篇日记",
    "记录一篇日记",
    "写一篇日记",
    "写篇日记",
    "记一篇日记",
    "记下来",
    "记一下",
    "记下今天",
    "帮我记录",
    "记录一下今天",
    "存成日记",
    "记成日记",
    "写进日记",
    "记入日记",
    "帮我写日记",
    "生成日记",
    "录入日记",
)

INSIGHT_STRONG: tuple[str, ...] = (
    "洞悉",
    "分析一下我",
    "帮我分析一下",
    "帮我分析",
    "我怎么了",
    "我到底怎么了",
    "我为什么会这样",
    "为什么我总是",
    "我是个什么样的人",
    "我是什么样的人",
    "帮我理清",
    "理清自己",
    "搞不懂自己",
    "不理解自己",
    "我到底想要什么",
    "不知道自己",
    "觉察一下",
    "我的心理",
    "什么心理",
)

PLAN_STRONG: tuple[str, ...] = (
    "做个计划",
    "做个规划",
    "制定一个计划",
    "制定计划",
    "制定个计划",
    "立个计划",
    "帮我做个计划",
    "帮我制定计划",
    "帮我规划",
    "学习计划",
    "健身计划",
    "减肥计划",
)

#: Plan-affordance patterns that warrant the LLM fallback — a numeric goal
#: ("30天", "每天4小时") plus a self-change verb.
PLAN_GOAL_PATTERN = re.compile(
    r"(坚持|养成|开始|想要?|打算|计划|学.{0,4}[会|剪辑|技能|东西])"
    r".{0,12}"
    r"(\d{1,4}\s*[天日周月]|每天|每日|小时|[0-9]+\s*天)"
    r"|(\d{1,4}\s*[天日])\s*(计划|打卡|挑战)"
    r"|(每天|每日).{0,10}(\d+(\.\d+)?)\s*(小时|h|H)"
    r"|(学会|学习|想学|开始学)"
)

#: Weak signals that alone don't justify a skill but make the LLM fallback
#: worth one light call. Emotional vocabulary feeds the insight path.
WEAK_SIGNALS: tuple[str, ...] = (
    "帮我",
    "我想",
    "我要",
    "我想开始",
    "为什么",
    "怎么才能",
    "计划",
    "坚持",
    "养成",
    "学会",
    "学习",
    "减肥",
    "打卡",
    "心理",
    "情绪",
    "感觉",
    "感到",
    "焦虑",
    "担心",
    "压力",
    "迷茫",
    "失眠",
    "睡不着",
    "难过",
    "低落",
    "烦",
    "日记",
    "记录",
    "分析",
    "洞察",
    "习惯",
)


@dataclass(frozen=True, slots=True)
class IntentDecision:
    intent: str  # one of USER_INTENTS
    source: str  # "rule" | "goal_rule" | "llm" | "default"


def _match_strong(text: str) -> str | None:
    if any(pattern in text for pattern in RECORD_STRONG):
        return "record"
    if any(pattern in text for pattern in PLAN_STRONG):
        return "plan"
    if any(pattern in text for pattern in INSIGHT_STRONG):
        return "insight"
    return None


def _has_weak_signal(text: str) -> bool:
    return any(signal in text for signal in WEAK_SIGNALS)


_INTENT_LLM_PROMPT = """判断用户这句话最想做什么，四选一：

- record：要求把今天发生的事写成日记、记录下来存档
- insight：想被分析心理、理清自己的感受、情绪或行为模式
- plan：想制定一个计划、开始坚持做某事、养成习惯、学一项技能
- chat：普通聊天、倾诉、提问、或其他

只输出一个小写单词：record / insight / plan / chat，不要任何其他内容。

用户输入：{content}
"""


def classify_user_intent(
    text: str,
    llm: LLMClient | None = None,
) -> IntentDecision:
    """Route *text* to one of the user skills, or ``"chat"``.

    Strong rules first; a goal-shaped plan sentence routes to ``plan``; a
    weak signal triggers the light-LLM fallback; anything else is chat.
    """
    text = (text or "").strip()
    if not text:
        return IntentDecision(intent="chat", source="default")

    strong = _match_strong(text)
    if strong is not None:
        return IntentDecision(intent=strong, source="rule")

    if PLAN_GOAL_PATTERN.search(text):
        return IntentDecision(intent="plan", source="goal_rule")

    if not _has_weak_signal(text):
        return IntentDecision(intent="chat", source="default")

    if llm is None:
        return IntentDecision(intent="chat", source="default")

    try:
        response = llm.invoke(_INTENT_LLM_PROMPT.format(content=text[:500]))
        answer = message_text(response).strip().lower()
        for intent in USER_INTENTS:
            if intent in answer:
                return IntentDecision(intent=intent, source="llm")
    except Exception as exc:
        logger.info("intent LLM fallback failed: %s", exc)
    return IntentDecision(intent="chat", source="default")
