"""Unit tests for the shared token estimator."""

from __future__ import annotations

from app.shared.token_utils import estimate_tokens


def test_empty_text_is_zero() -> None:
    assert estimate_tokens("") == 0


def test_chinese_weighs_more_than_ascii() -> None:
    chinese = estimate_tokens("今天天气真好啊")  # 7 chars * 1.5
    english = estimate_tokens("the weather is nice")
    assert chinese > 0
    assert english > 0
    # 7 Chinese chars (~10.5 tokens) outweigh ~15 ascii letters (~3.75 tokens).
    assert chinese > english


def test_estimate_grows_with_length() -> None:
    short = estimate_tokens("失眠")
    long = estimate_tokens("失眠" * 50)
    assert long > short


def test_mixed_text_counts_all_segments() -> None:
    # Chinese + ascii + punctuation/digits all contribute.
    assert estimate_tokens("今天 day 123！") > estimate_tokens("今天")
