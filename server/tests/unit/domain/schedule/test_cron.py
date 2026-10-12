"""Tests for the minimal 5-field cron parser (A4)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domain.schedule.cron import next_run_after, parse_cron, validate_cron


def test_parse_all_wildcards() -> None:
    spec = parse_cron("* * * * *")
    assert spec.minute == frozenset(range(60))
    assert spec.hour == frozenset(range(24))
    assert not spec.day_restricted
    assert not spec.weekday_restricted


def test_parse_ranges_steps_and_lists() -> None:
    spec = parse_cron("*/15 9-17 1,15 * 1-5")
    assert spec.minute == frozenset({0, 15, 30, 45})
    assert spec.hour == frozenset(range(9, 18))
    assert spec.day == frozenset({1, 15})
    assert spec.weekday == frozenset({1, 2, 3, 4, 5})
    assert spec.day_restricted
    assert spec.weekday_restricted


def test_weekday_seven_normalized_to_sunday() -> None:
    assert parse_cron("0 9 * * 7").weekday == frozenset({0})


@pytest.mark.parametrize(
    "expr",
    [
        "* * * *",  # too few fields
        "* * * * * *",  # too many fields
        "60 * * * *",  # minute out of range
        "* 24 * * *",  # hour out of range
        "0 0 0 * *",  # day-of-month below minimum
        "* * * 13 *",  # month out of range
        "* * * * 8",  # weekday out of range
        "*/0 * * * *",  # zero step
        "a * * * *",  # non-numeric
    ],
)
def test_parse_rejects_malformed(expr: str) -> None:
    with pytest.raises(ValueError):
        parse_cron(expr)


def test_validate_cron_trims() -> None:
    assert validate_cron("  0 9 * * *  ") == "0 9 * * *"


def test_next_run_daily() -> None:
    # 2026-10-11 is a Sunday.
    after = datetime(2026, 10, 11, 8, 30)
    assert next_run_after("0 9 * * *", after) == datetime(2026, 10, 11, 9, 0)


def test_next_run_rolls_to_tomorrow_when_past_today() -> None:
    after = datetime(2026, 10, 11, 9, 0)
    assert next_run_after("0 9 * * *", after) == datetime(2026, 10, 12, 9, 0)


def test_next_run_every_15_minutes() -> None:
    after = datetime(2026, 10, 11, 10, 7)
    assert next_run_after("*/15 * * * *", after) == datetime(2026, 10, 11, 10, 15)


def test_next_run_first_of_month() -> None:
    after = datetime(2026, 10, 11, 0, 0)
    assert next_run_after("0 0 1 * *", after) == datetime(2026, 11, 1, 0, 0)


def test_next_run_weekday_monday() -> None:
    after = datetime(2026, 10, 11, 10, 0)  # Sunday
    assert next_run_after("0 9 * * 1", after) == datetime(2026, 10, 12, 9, 0)


def test_next_run_sunday_via_seven() -> None:
    after = datetime(2026, 10, 11, 10, 0)  # Sunday, past 09:00
    assert next_run_after("0 9 * * 7", after) == datetime(2026, 10, 18, 9, 0)


def test_dom_and_weekday_combine_with_or() -> None:
    # day-of-month=15 OR Monday → the Monday (Oct 12) wins over the 15th.
    after = datetime(2026, 10, 11, 0, 0)
    assert next_run_after("0 9 15 * 1", after) == datetime(2026, 10, 12, 9, 0)


def test_only_dom_restricted_must_match() -> None:
    after = datetime(2026, 10, 11, 0, 0)
    assert next_run_after("0 9 15 * *", after) == datetime(2026, 10, 15, 9, 0)


def test_next_run_impossible_date_raises() -> None:
    with pytest.raises(ValueError):
        next_run_after("0 0 30 2 *", datetime(2026, 1, 1, 0, 0))