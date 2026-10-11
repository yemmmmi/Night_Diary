"""Trust boundary for tool / external content entering the LLM context.

Everything a tool returns — MCP servers, web fetches, third-party APIs — is
*data*, never instructions. :func:`scan_for_injection` flags instruction-
injection markers and :func:`wrap_untrusted` fences the payload in an explicit
untrusted envelope so the model treats it as inert content rather than a
directive. Mirrors Hermes' context-file injection scanning at the tool layer.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Envelope tag name. Kept ASCII-only so the model can recognise it reliably.
UNTRUSTED_TAG = "tool_output"

#: Fullwidth colon, written as an escape so the source stays ASCII-clean.
_FW_COLON = "\uFF1A"

#: Instruction-injection markers, matched case-insensitively (EN + ZH).
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(
            r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+instructions?",
            re.IGNORECASE,
        ),
    ),
    (
        "disregard_instructions",
        re.compile(
            r"disregard\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+"
            r"(instructions?|rules?|prompts?)",
            re.IGNORECASE,
        ),
    ),
    ("forget_context", re.compile(r"forget\s+(everything|all|your|the)\b", re.IGNORECASE)),
    ("new_instructions", re.compile(rf"new\s+instructions?\s*[:{_FW_COLON}]", re.IGNORECASE)),
    ("you_are_now", re.compile(r"you\s+are\s+now\b", re.IGNORECASE)),
    ("system_prompt", re.compile(r"system\s+prompt", re.IGNORECASE)),
    (
        "reveal_prompt",
        re.compile(
            r"(reveal|show|print|repeat|output)\s+(me\s+)?(your\s+)?"
            r"(system\s+)?(prompt|instructions?)",
            re.IGNORECASE,
        ),
    ),
    (
        "do_not_tell_user",
        re.compile(r"do\s+not\s+(tell|inform|mention)\s+(the\s+)?user", re.IGNORECASE),
    ),
    ("role_tag", re.compile(r"<\s*/?\s*(system|assistant)\s*>", re.IGNORECASE)),
    ("zh_ignore", re.compile(r"忽略(以上|之前|前面|上面)(的)?(所有|全部)?(指令|要求|提示)")),
    ("zh_forget", re.compile(r"忘记(之前|以上|前面|所有|全部)")),
    ("zh_you_are_now", re.compile(r"你现在(是|扮演|开始)")),
    ("zh_system_prompt", re.compile(r"(系统|初始)(提示词|提示|指令)")),
    ("zh_new_instructions", re.compile(rf"新的?(指令|要求|规则|提示)[:{_FW_COLON}]")),
    ("zh_override", re.compile(r"(覆盖|绕过|突破|忽略)(安全|限制|规则|约束)")),
)


@dataclass(frozen=True, slots=True)
class InjectionScan:
    """Result of scanning untrusted text for instruction-injection markers."""

    suspicious: bool
    matches: tuple[str, ...]


def scan_for_injection(text: str) -> InjectionScan:
    """Return which injection markers (if any) ``text`` contains."""
    if not text:
        return InjectionScan(suspicious=False, matches=())
    found = [name for name, pattern in _INJECTION_PATTERNS if pattern.search(text)]
    return InjectionScan(suspicious=bool(found), matches=tuple(found))


def wrap_untrusted(text: str, *, source: str) -> str:
    """Fence ``text`` in an untrusted envelope, flagging injection markers.

    The envelope makes the trust level explicit to the model. Any literal
    closing tag inside the payload is neutralised so content cannot break out
    of the fence.
    """
    scan = scan_for_injection(text)
    safe = str(text).replace(f"</{UNTRUSTED_TAG}>", f"<\\/{UNTRUSTED_TAG}>")
    attribute_source = source.replace('"', "'")
    flag = ' flag="suspicious"' if scan.suspicious else ""
    if scan.suspicious:
        logger.warning(
            "Untrusted content from '%s' flagged for instruction injection: %s",
            source,
            ", ".join(scan.matches),
        )
    return (
        f'<{UNTRUSTED_TAG} source="{attribute_source}" trust="untrusted"{flag}>\n'
        f"{safe}\n"
        f"</{UNTRUSTED_TAG}>"
    )


__all__ = ["UNTRUSTED_TAG", "InjectionScan", "scan_for_injection", "wrap_untrusted"]