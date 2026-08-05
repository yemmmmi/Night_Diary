"""在领域模块间共享的 token 估算辅助函数。"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """估算中英混合日记文本的 token 数量。

    中文字符约使用 1.5 个 token，ASCII 字母每个约 0.25 个 token，
    其他字符约 0.5 个 token。
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
