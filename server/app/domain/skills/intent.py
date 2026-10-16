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

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.shared.llm import LLMClient, message_text

logger = logging.getLogger(__name__)

USER_INTENTS = ("record", "insight", "plan", "chat")

#: Intents that actually *do* something (write a diary / analyse / build a
#: plan). Only these are worth a clarifying question when the router is
#: unsure — a low-confidence ``chat`` degrades silently to normal chat.
SKILL_INTENTS = ("record", "insight", "plan")

#: Below this router confidence a leaning-toward-a-skill answer is treated as
#: a guess and the user is asked to disambiguate instead.
CLARIFY_THRESHOLD = 0.5

#: Confidence when the router LLM returns a bare intent word without a score.
_DEFAULT_LLM_CONFIDENCE = 0.7

#: Confidence for a degraded (no-LLM / unparseable) routing decision.
_AMBIGUOUS_CONFIDENCE = 0.3

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
    "怎么规划",
    "如何规划",
    "列个计划",
    "列一份计划",
    "列哪些计划",
    "列一下计划",
    "帮我列计划",
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
    source: str  # "rule" | "goal_rule" | "llm" | "default" | "manual"
    confidence: float = 1.0
    #: The router's explicit "I cannot tell whether this is a skill or plain
    #: chat" answer. ``None`` means the router did not answer that question
    #: (older contract / bare intent word) and the confidence heuristic applies.
    ambiguous: bool | None = None

    @property
    def should_clarify(self) -> bool:
        """True when the router was not confident enough to act on its guess.

        Only an LLM answer can be uncertain enough to warrant asking — a
        strong rule, a goal-shaped plan sentence or a manual selection is
        always trusted.
        """
        if self.source != "llm":
            return False
        # The router explicitly judged the message ambiguous — but only a lean
        # toward a *skill* is worth interrupting for. An ambiguous message the
        # router still read as chat gets a normal reply: nothing is written, so
        # there is no wrong proposal to prevent, and a disambiguation card would
        # be a gratuitous interruption (that is what the false-clarification
        # rate measures).
        if self.ambiguous is not None:
            return self.ambiguous and self.intent in SKILL_INTENTS
        # Older contract: no ambiguity flag, so fall back to the confidence
        # heuristic.
        return self.intent in SKILL_INTENTS and self.confidence < CLARIFY_THRESHOLD


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

{catalog}
只输出一个 JSON，不要任何其他内容：
{{"intent": "record / insight / plan / chat", "confidence": 0.0 到 1.0, "ambiguous": true 或 false}}

confidence 是你的把握程度：很确定给 0.9 以上；如果用户意图模棱两可、你只是勉强猜的，给 0.5 以下。

ambiguous 表示"我拿不准这句该走技能还是普通聊天"：
- 有明确诉求对象或产出的不算歧义，给 false（例：「分析我最近到底在想什么」「把这段心路历程留下来」「理一下接下来要做的事」「怎么调整作息」）
- 只是模糊指代或没讲清要干什么的算歧义，给 true（例：「帮我看看这段」「帮我整理下这个想法」「最近压力有点大」）
intent 仍要给出一个最可能的选择；ambiguous 只额外说明你有多拿不准。

用户输入：{content}
"""


def _match_intent_word(text: str) -> str | None:
    """Return the first known intent word contained in *text*, or None."""
    for intent in USER_INTENTS:
        if intent in text:
            return intent
    return None


def _coerce_confidence(value: Any) -> float:
    """Clamp *value* into [0, 1], falling back to the default on garbage."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return _DEFAULT_LLM_CONFIDENCE


def _parse_ambiguity(value: Any) -> bool | None:
    """Tri-state parse of the router's ``ambiguous`` flag.

    ``True``/``False`` when the router answered the explicit question, ``None``
    when the field is missing or unusable — the caller then falls back to the
    confidence heuristic instead of silently treating "absent" as "not ambiguous".
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    return None


def _parse_llm_answer(answer: str) -> tuple[str | None, float, bool | None]:
    """Parse the router LLM reply into ``(intent, confidence, ambiguous)``.

    Accepts the JSON contract (``{"intent": ..., "confidence": ..., "ambiguous": ...}``)
    and, for robustness, a bare intent word (older prompt / mock).

    ``ambiguous`` is tri-state: ``True``/``False`` when the router answered the
    explicit ambiguity question, ``None`` when the field is absent — in which
    case the caller falls back to the confidence heuristic so the older contract
    (and the eval's stub oracle) keeps working unchanged.
    """
    cleaned = (answer or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError, TypeError):
        data = None

    if isinstance(data, dict):
        intent = _match_intent_word(str(data.get("intent", "")).strip().lower())
        return (
            intent,
            _coerce_confidence(data.get("confidence")),
            _parse_ambiguity(data.get("ambiguous")),
        )
    return _match_intent_word(cleaned.lower()), _DEFAULT_LLM_CONFIDENCE, None


def classify_user_intent(
    text: str,
    llm: LLMClient | None = None,
    *,
    skill_catalog: str = "",
) -> IntentDecision:
    """Route *text* to one of the user skills, or ``"chat"``.

    Strong rules first; a goal-shaped plan sentence routes to ``plan``; a
    weak signal triggers the light-LLM fallback; anything else is chat.

    *skill_catalog* is the Level-0 skill metadata block injected into the
    fallback prompt so the router sees the registered skills (and their
    descriptions) instead of a fixed hard-coded list.
    """
    text = (text or "").strip()
    if not text:
        return IntentDecision(intent="chat", source="default", confidence=1.0)

    strong = _match_strong(text)
    if strong is not None:
        return IntentDecision(intent=strong, source="rule", confidence=0.95)

    if PLAN_GOAL_PATTERN.search(text):
        return IntentDecision(intent="plan", source="goal_rule", confidence=0.9)

    if not _has_weak_signal(text):
        return IntentDecision(intent="chat", source="default", confidence=1.0)

    if llm is None:
        return IntentDecision(
            intent="chat", source="default", confidence=_AMBIGUOUS_CONFIDENCE
        )

    try:
        prompt = _INTENT_LLM_PROMPT.format(content=text[:500], catalog=skill_catalog)
        response = llm.invoke(prompt)
        intent, confidence, ambiguous = _parse_llm_answer(message_text(response))
        if intent is not None:
            return IntentDecision(
                intent=intent, source="llm", confidence=confidence, ambiguous=ambiguous
            )
    except Exception as exc:
        logger.info("intent LLM fallback failed: %s", exc)
    return IntentDecision(intent="chat", source="default", confidence=_AMBIGUOUS_CONFIDENCE)
