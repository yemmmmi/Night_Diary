"""InputPreprocessor — scene-2 input preprocessing layer.

Sits before ChatIntentClassifier in the conversation pipeline. Its job is:

1. **Text cleaning**: strip HTML tags, control characters, excess whitespace.
2. **NFC normalization**: unify Unicode composed forms (important for CJK).
3. **Security check**: detect prompt-injection patterns and flag sensitive info
   (phone numbers, ID cards, bank cards). Does NOT block — only flags.
4. **Omission completion**: lightweight rule-based completion when the user
   references something from context ("那呢" → append context keyword).
5. **Negation detection**: detect corrections to previous turns
   ("不不不", "不是", "说错了") so downstream can adjust.

All operations are zero-token (pure regex/string ops) — no LLM calls.
The preprocessor is intentionally lightweight; heavy semantic understanding
is handled by QueryUnderstander and ChatIntentClassifier downstream.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Text cleaning patterns ──────────────────────────────────────────

# HTML tags (basic — not a full parser, sufficient for chat input)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Control characters (except \n \t \r which are valid whitespace)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Excess whitespace: 3+ consecutive newlines → 2, 2+ spaces → 1
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[^\S\n]{2,}")

# Zero-width characters (common in copy-pasted text)
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")

# ── Security patterns ───────────────────────────────────────────────

# Prompt injection patterns (common attack vectors)
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all\s+previous)", re.IGNORECASE),
]

# Sensitive info patterns (Chinese context)
# Use lookaround instead of \b since \b doesn't work well with CJK characters
# Phone: 11 digits starting with 1
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# ID card: 18 digits, last may be X
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
# Bank card: 16-19 digits
_BANK_CARD_RE = re.compile(r"(?<!\d)\d{16,19}(?!\d)")

# ── Omission / negation patterns ────────────────────────────────────

# Omission markers — user references something from context without stating it
_OMISSION_MARKERS = [
    "那呢",
    "那个呢",
    "那怎么样",
    "然后呢",
    "后来呢",
    "它呢",
    "他呢",
    "她呢",
]

# Negation / correction markers
_NEGATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*(不不不|不是不是|说错了|搞错了|不对不对)"),
    re.compile(r"^\s*(不是|不对|错了)\s*[,，]"),
    re.compile(r"^\s*(我说的不是|我的意思不是)"),
    re.compile(r"^\s*(算了|当我没说)"),
]


@dataclass
class SecurityFlags:
    """Security check results — flags only, does not block."""

    has_injection: bool = False
    injection_patterns: list[str] = field(default_factory=list)
    has_sensitive_info: bool = False
    sensitive_types: list[str] = field(default_factory=list)
    # Masked text if sensitive info was found (original otherwise)
    masked_text: str = ""


@dataclass
class PreprocessResult:
    """Result of input preprocessing."""

    clean_text: str
    original_text: str
    security_flags: SecurityFlags
    negation_detected: bool
    omission_detected: bool
    # If omission was detected, a context keyword was appended
    context_appended: str = ""


class InputPreprocessor:
    """Input preprocessing layer for scene 2 (multi-turn conversation).

    All methods are zero-token (pure regex/string operations). The preprocessor
    cleans, normalizes, and flags input but does NOT block it — downstream
    components (CrisisGuard, ChatIntentClassifier) handle blocking decisions.

    Usage::

        preprocessor = InputPreprocessor()
        result = preprocessor.process(content, context=brief_context)
        content = result.clean_text  # Use cleaned text downstream
    """

    def process(self, content: str, *, context: str = "") -> PreprocessResult:
        """Run full preprocessing pipeline.

        Args:
            content: Raw user input.
            context: Recent conversation history (for omission completion).

        Returns:
            PreprocessResult with cleaned text and flags.
        """
        if not content or not content.strip():
            return PreprocessResult(
                clean_text=content.strip() if content else "",
                original_text=content,
                security_flags=SecurityFlags(masked_text=content.strip() if content else ""),
                negation_detected=False,
                omission_detected=False,
            )

        original = content

        # 1. Text cleaning
        cleaned = self._clean_text(content)

        # 2. NFC normalization
        normalized = self._normalize_unicode(cleaned)

        # 3. Security check
        security_flags = self._security_check(normalized)

        # Use masked text if sensitive info was found
        working_text = security_flags.masked_text or normalized

        # 4. Omission completion
        omission_detected, completed, context_appended = self._complete_omission(
            working_text, context
        )

        # 5. Negation detection
        negation_detected = self._detect_negation(completed)

        return PreprocessResult(
            clean_text=completed,
            original_text=original,
            security_flags=security_flags,
            negation_detected=negation_detected,
            omission_detected=omission_detected,
            context_appended=context_appended,
        )

    def _clean_text(self, text: str) -> str:
        """Remove HTML tags, control characters, zero-width chars, excess whitespace."""
        # Remove zero-width characters
        text = _ZERO_WIDTH_RE.sub("", text)
        # Remove HTML tags
        text = _HTML_TAG_RE.sub("", text)
        # Remove control characters (keep \n \t \r)
        text = _CONTROL_CHAR_RE.sub("", text)
        # Normalize whitespace
        text = _MULTI_NEWLINE_RE.sub("\n\n", text)
        text = _MULTI_SPACE_RE.sub(" ", text)
        # Strip leading/trailing whitespace
        return text.strip()

    def _normalize_unicode(self, text: str) -> str:
        """Apply NFC normalization to unify Unicode composed forms."""
        return unicodedata.normalize("NFC", text)

    def _security_check(self, text: str) -> SecurityFlags:
        """Check for prompt injection and sensitive information.

        Does NOT block — only flags. Sensitive info is masked in the returned text.
        """
        flags = SecurityFlags(masked_text=text)

        # Prompt injection detection
        for pattern in _INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                flags.has_injection = True
                flags.injection_patterns.append(match.group())

        if flags.has_injection:
            logger.warning(
                "input.injection_detected patterns=%s text_digest=%s",
                flags.injection_patterns,
                text[:80],
            )

        # Sensitive info detection and masking
        masked = text
        sensitive_found = False

        # Phone numbers
        if _PHONE_RE.search(masked):
            flags.has_sensitive_info = True
            flags.sensitive_types.append("phone")
            masked = _PHONE_RE.sub("[手机号]", masked)
            sensitive_found = True

        # ID cards
        if _ID_CARD_RE.search(masked):
            flags.has_sensitive_info = True
            flags.sensitive_types.append("id_card")
            masked = _ID_CARD_RE.sub("[身份证]", masked)
            sensitive_found = True

        # Bank cards (only if not already masked as phone/id)
        if _BANK_CARD_RE.search(masked) and not sensitive_found:
            # Be conservative — only flag 16-19 digit sequences that aren't phone/id
            flags.has_sensitive_info = True
            flags.sensitive_types.append("bank_card")
            masked = _BANK_CARD_RE.sub("[卡号]", masked)

        if flags.has_sensitive_info:
            logger.info(
                "input.sensitive_detected types=%s — masked",
                flags.sensitive_types,
            )

        flags.masked_text = masked
        return flags

    def _complete_omission(self, text: str, context: str) -> tuple[bool, str, str]:
        """Detect omission markers and append context keywords.

        Lightweight rule-based approach: if the user's message contains an
        omission marker ("那呢", "然后呢"), extract the first keyword from
        the conversation context and append it.

        Returns (omission_detected, completed_text, context_keyword_appended).
        """
        if not context or not context.strip():
            return False, text, ""

        text_lower = text.strip()
        omission_found = None
        for marker in _OMISSION_MARKERS:
            if marker in text_lower:
                omission_found = marker
                break

        if omission_found is None:
            return False, text, ""

        # Extract first meaningful line from context (skip headers like 【...】)
        context_lines = context.split("\n")
        context_keyword = ""
        for line in context_lines:
            line = line.strip()
            if not line or line.startswith("【") or line.startswith("-"):
                continue
            # Take first 20 chars of the first meaningful line
            context_keyword = line[:20]
            break

        if not context_keyword:
            return True, text, ""

        # Append context keyword to help downstream understanding
        completed = f"{text} （上下文参考：{context_keyword}）"
        logger.debug(
            "input.omission_completed marker=%s keyword=%s",
            omission_found,
            context_keyword,
        )
        return True, completed, context_keyword

    def _detect_negation(self, text: str) -> bool:
        """Detect negation/correction patterns at the start of the message."""
        for pattern in _NEGATION_PATTERNS:
            if pattern.search(text):
                logger.debug("input.negation_detected text_digest=%s", text[:50])
                return True
        return False


__all__ = ["InputPreprocessor", "PreprocessResult", "SecurityFlags"]
