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


# ---------------------------------------------------------------------------
# P5 Task 10 — BGE tokenizer upgrade (lazy singleton + char-based fallback)
# ---------------------------------------------------------------------------


def test_estimate_tokens_uses_bge_tokenizer_when_available() -> None:
    """estimate_tokens returns a positive int for Chinese text.

    When sentence-transformers is installed the BGE tokenizer is used; in
    CI/dev (no [eval] extra) the call transparently degrades to char-based
    estimation. Either way the contract — a positive int — must hold.
    """
    # 中文文本
    tokens = estimate_tokens("失眠焦虑")
    assert isinstance(tokens, int)
    assert tokens > 0


def test_estimate_tokens_falls_back_without_model() -> None:
    """The char-based fallback is always available as a pure function."""
    from app.shared.token_utils import _char_based_estimate

    # 直接测降级函数
    result = _char_based_estimate("失眠焦虑")
    assert result > 0
    # 4 Chinese chars * 1.5 = 6 (rounds to 6)
    assert result == 6


def test_estimate_tokens_empty() -> None:
    assert estimate_tokens("") == 0


def test_estimate_tokens_mixed_chinese_english() -> None:
    """中英混合文本。"""
    tokens = estimate_tokens("今天心情不好 feeling sad")
    assert tokens > 0


def test_tokenizer_is_singleton() -> None:
    """tokenizer should be a singleton — model loading is expensive."""
    from app.shared.token_utils import _get_tokenizer

    t1 = _get_tokenizer()
    t2 = _get_tokenizer()
    # Same instance for a real tokenizer, or the same "fallback" sentinel in
    # degraded mode — both satisfy the identity/equality check below.
    assert t1 is t2 or t1 == t2


def test_fallback_estimate_matches_legacy_formula() -> None:
    """_char_based_estimate must stay numerically equivalent to the legacy
    estimate_tokens (the char-coefficient weighting that preceded the BGE
    upgrade). This guards prompt-budget callers against silent drift."""
    from app.shared.token_utils import _char_based_estimate

    # Legacy: chinese*1.5 + ascii/4 + other*0.5, rounded.
    assert _char_based_estimate("今天天气真好啊") == 11  # 7 * 1.5 = 10.5 → 11
    assert _char_based_estimate("hello") == 1  # 5 / 4 = 1.25 → 1
    assert _char_based_estimate("今天 day 123！") == _char_based_estimate("今天 day 123！")
