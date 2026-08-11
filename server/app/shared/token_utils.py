"""Token estimation utilities.

Uses BGE tokenizer (bge-small-zh-v1.5) when sentence-transformers is
available for accurate Chinese/mixed token counting. Falls back to
character-coefficient estimation otherwise.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_tokenizer: Any = None  # lazy singleton (real tokenizer once loaded)
_fallback_mode: bool | None = None  # None = unchecked, True = fallback, False = real


def _get_tokenizer() -> Any:
    """Lazy-load the BGE tokenizer as a singleton.

    Returns the tokenizer object when ``sentence-transformers`` is installed,
    or the sentinel string ``"fallback"`` when it is unavailable. The result
    is cached so the (expensive) model load happens at most once per process.
    """
    global _tokenizer, _fallback_mode
    if _fallback_mode is not None:
        return _tokenizer if _fallback_mode is False else "fallback"
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        _tokenizer = model.tokenizer
        _fallback_mode = False
        logger.info("Loaded BGE tokenizer for token estimation")
        return _tokenizer
    except Exception as exc:
        logger.info("sentence-transformers unavailable, using char-based fallback: %s", exc)
        _fallback_mode = True
        return "fallback"


def _char_based_estimate(text: str) -> int:
    """Character-coefficient estimation (fallback when no tokenizer).

    Numerically equivalent to the legacy ``estimate_tokens``: Chinese
    characters use ~1.5 tokens, ASCII letters ~0.25 tokens each, and other
    characters ~0.5 tokens.
    """
    if not text:
        return 0

    chinese_chars = 0
    ascii_chars = 0
    other_chars = 0

    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            chinese_chars += 1
        elif ch.isascii() and ch.isalpha():
            ascii_chars += 1
        else:
            other_chars += 1

    english_tokens = ascii_chars / 4.0
    chinese_tokens = chinese_chars * 1.5
    other_tokens = other_chars * 0.5

    return int(chinese_tokens + english_tokens + other_tokens + 0.5)


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses the BGE tokenizer when available, falls back to character-coefficient
    estimation. Safe for prompt budget control and streaming cost estimation.
    """
    if not text:
        return 0
    tok = _get_tokenizer()
    if tok == "fallback":
        return _char_based_estimate(text)
    try:
        return len(tok.encode(text, add_special_tokens=False))
    except Exception:
        return _char_based_estimate(text)
