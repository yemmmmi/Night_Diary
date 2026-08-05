"""Token estimation helpers shared across domain modules."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English diary text.

    Chinese characters use ~1.5 tokens, ASCII letters ~0.25 tokens each,
    and other characters ~0.5 tokens.
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
