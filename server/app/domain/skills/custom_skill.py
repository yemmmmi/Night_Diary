"""User-defined custom skills — bounded, reviewed, read-only at reply time (A2).

Hermes lets its agent create / edit / delete arbitrary skills. 夜记 deliberately
does **not** open that door: a custom skill here is a *reply-shaping advisory*
the user authors by hand (settings), reviewed for safety on every write, and
loaded **read-only** at reply time. The agent has no tool that can create or
modify a custom skill, so the "提案-确认、Agent 零写权限" invariant holds.

A custom skill carries:

* ``name`` / ``description`` — human identity shown in settings;
* ``triggers`` — substrings that, when present in the user's message, activate
  the skill for that turn (e.g. 跑步 → 配速建议);
* ``instruction`` — natural-language guidance injected into the reply prompt
  (volatile, after the frozen prefix) only when triggered.

:func:`review_custom_skill` is the safety gate: it rejects definitions that try
to override the global tone baseline, coerce/pressure the user, disable the
crisis mechanism, or instruct tool/write actions. Review is deterministic and
keyword-based so it is cheap and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Field budgets (characters, not tokens) — keep a custom skill tiny so it can
#: never bloat the reply prompt.
MAX_NAME_CHARS = 40
MAX_DESCRIPTION_CHARS = 120
MAX_INSTRUCTION_CHARS = 500
MAX_TRIGGER_CHARS = 20
MAX_TRIGGERS = 8

#: Runtime caps for the injected block.
MAX_MATCHED_SKILLS = 3
MAX_BLOCK_CHARS = 900


@dataclass(frozen=True, slots=True)
class CustomSkillDefinition:
    """A user-authored, reviewed custom skill (read-only at reply time)."""

    skill_id: int
    user_id: str
    name: str
    description: str
    triggers: tuple[str, ...]
    instruction: str
    enabled: bool
    version: int
    created_at: float
    updated_at: float


@dataclass(frozen=True, slots=True)
class ReviewViolation:
    """One reason a definition was rejected."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """Outcome of :func:`review_custom_skill`."""

    ok: bool
    violations: tuple[ReviewViolation, ...] = field(default_factory=tuple)


#: ``(code, message, pattern)`` — the definition text (name + description +
#: triggers + instruction) must not match any of these. Patterns are matched
#: case-insensitively against the concatenated text.
_FORBIDDEN_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        "tone_override",
        "不得修改、覆盖或忽略全局语气与系统设定",
        r"忽略(之前|上述|以上|所有)?(的)?(系统|指令|设定|提示)"
        r"|无视(系统|指令|设定)"
        r"|覆盖(系统|全局)?(设定|语气|提示)"
        r"|改变全局语气"
        r"|越狱|jailbreak"
        r"|ignore\s+(all\s+)?(previous|above|system)"
        r"|override\s+(the\s+)?(system|prompt)",
    ),
    (
        "coercion",
        "不得包含施压、威胁或强迫性表达",
        r"威胁|逼迫|施压|恐吓|惩罚|必须立刻|否则就|你若不",
    ),
    (
        "safety_override",
        "不得关闭或绕过危机与安全机制",
        r"忽略危机|关闭(安全|危机)|跳过(安全|危机)|不做危机",
    ),
    (
        "unsafe_action",
        "不得指示调用工具或执行写入 / 删除等动作",
        r"执行工具|调用工具|运行命令|删除(数据|记录|日记)|清空全部|drop\s+table|rm\s+-rf|修改数据库|写入数据库",
    ),
)

#: Compiled once at import time.
_COMPILED_PATTERNS = tuple(
    (code, message, re.compile(pattern, re.IGNORECASE))
    for code, message, pattern in _FORBIDDEN_PATTERNS
)


def normalize_triggers(raw: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Trim, drop empties, de-duplicate (case-insensitively), and cap length.

    Order is preserved so the user's intent is stable across edits.
    """
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        trigger = (item or "").strip()[:MAX_TRIGGER_CHARS]
        if not trigger:
            continue
        key = trigger.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(trigger)
    return tuple(result[:MAX_TRIGGERS])


def review_custom_skill(
    *,
    name: str,
    description: str,
    triggers: list[str] | tuple[str, ...],
    instruction: str,
) -> ReviewResult:
    """Safety-review a custom skill definition.

    Returns ``ReviewResult(ok=True, ...)`` when the definition is acceptable;
    otherwise the violations explain exactly what must change. This is the gate
    the API calls before persisting any create/update.
    """
    violations: list[ReviewViolation] = []

    clean_name = (name or "").strip()
    clean_description = (description or "").strip()
    clean_instruction = (instruction or "").strip()
    clean_triggers = normalize_triggers(triggers)

    if not clean_name:
        violations.append(ReviewViolation("name_required", "技能名称不能为空"))
    elif len(clean_name) > MAX_NAME_CHARS:
        violations.append(
            ReviewViolation("name_too_long", f"技能名称不得超过 {MAX_NAME_CHARS} 字")
        )

    if len(clean_description) > MAX_DESCRIPTION_CHARS:
        violations.append(
            ReviewViolation("description_too_long", f"描述不得超过 {MAX_DESCRIPTION_CHARS} 字")
        )

    if not clean_instruction:
        violations.append(ReviewViolation("instruction_required", "技能指令不能为空"))
    elif len(clean_instruction) > MAX_INSTRUCTION_CHARS:
        violations.append(
            ReviewViolation("instruction_too_long", f"技能指令不得超过 {MAX_INSTRUCTION_CHARS} 字")
        )

    if not clean_triggers:
        violations.append(ReviewViolation("triggers_required", "至少需要一个触发词"))
    elif len(triggers) > MAX_TRIGGERS:
        violations.append(
            ReviewViolation("too_many_triggers", f"触发词不得超过 {MAX_TRIGGERS} 个")
        )

    haystack = " ".join((clean_name, clean_description, " ".join(clean_triggers), clean_instruction))
    for code, message, pattern in _COMPILED_PATTERNS:
        if pattern.search(haystack):
            violations.append(ReviewViolation(code, message))

    return ReviewResult(ok=not violations, violations=tuple(violations))


def match_triggers(triggers: tuple[str, ...], content: str) -> bool:
    """Whether any trigger occurs in *content* (case-insensitive substring)."""
    text = (content or "").casefold()
    if not text:
        return False
    return any(trigger.casefold() in text for trigger in triggers if trigger)


__all__ = [
    "MAX_BLOCK_CHARS",
    "MAX_DESCRIPTION_CHARS",
    "MAX_INSTRUCTION_CHARS",
    "MAX_MATCHED_SKILLS",
    "MAX_NAME_CHARS",
    "MAX_TRIGGERS",
    "MAX_TRIGGER_CHARS",
    "CustomSkillDefinition",
    "ReviewResult",
    "ReviewViolation",
    "match_triggers",
    "normalize_triggers",
    "review_custom_skill",
]