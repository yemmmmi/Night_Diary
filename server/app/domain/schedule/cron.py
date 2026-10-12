"""Minimal 5-field cron parser and next-run computation (A4).

Supports the subset the scheduled-task feature needs, with no third-party
dependency:

- ``*``          every value
- ``a``          a single value
- ``a-b``        an inclusive range
- ``*/n``        every ``n`` starting from the field minimum
- ``a-b/n``      every ``n`` within a range
- ``a,b,c``      a comma list of any of the above

Field order is the standard ``minute hour day-of-month month day-of-week``.
Day-of-week uses cron convention ``0`` = Sunday … ``6`` = Saturday (``7`` is
also accepted as Sunday). When **both** day-of-month and day-of-week are
restricted (neither is ``*``) they combine with OR (Vixie-cron semantics);
otherwise the restricted one must match.

All datetimes are naive and interpreted in the server's local time — the
scheduler runs against :func:`datetime.datetime.now`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# (name, minimum, maximum) for the five fields, in order.
_FIELD_BOUNDS: tuple[tuple[str, int, int], ...] = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("weekday", 0, 7),
)


def _parse_field(spec: str, lo: int, hi: int, name: str) -> set[int]:
    """Expand one cron field into the set of matching integers."""
    if not spec:
        raise ValueError(f"cron {name} 字段为空")
    values: set[int] = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            raise ValueError(f"cron {name} 字段无效: {spec!r}")
        step = 1
        if "/" in token:
            token, _, step_text = token.partition("/")
            if not step_text.isdigit() or int(step_text) <= 0:
                raise ValueError(f"cron {name} 步长无效: {step_text!r}")
            step = int(step_text)
        if token == "*":
            start, end = lo, hi
        elif "-" in token:
            start_text, _, end_text = token.partition("-")
            if not (start_text.isdigit() and end_text.isdigit()):
                raise ValueError(f"cron {name} 范围无效: {token!r}")
            start, end = int(start_text), int(end_text)
        elif token.isdigit():
            start = end = int(token)
        else:
            raise ValueError(f"cron {name} 字段无效: {token!r}")
        if start < lo or end > hi or start > end:
            raise ValueError(f"cron {name} 超出范围 {lo}-{hi}: {token!r}")
        values.update(range(start, end + 1, step))
    return values


@dataclass(frozen=True)
class CronSpec:
    """A parsed cron expression (sets are pre-expanded for matching)."""

    minute: frozenset[int]
    hour: frozenset[int]
    day: frozenset[int]
    month: frozenset[int]
    weekday: frozenset[int]
    day_restricted: bool
    weekday_restricted: bool
    source: str


def parse_cron(expr: str) -> CronSpec:
    """Parse a 5-field cron expression; raise ``ValueError`` when malformed."""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron 表达式必须是 5 个字段: 分 时 日 月 周")
    minute = _parse_field(parts[0], 0, 59, "minute")
    hour = _parse_field(parts[1], 0, 23, "hour")
    day = _parse_field(parts[2], 1, 31, "day")
    month = _parse_field(parts[3], 1, 12, "month")
    weekday = _parse_field(parts[4], 0, 7, "weekday")
    if 7 in weekday:
        weekday = (weekday - {7}) | {0}
    return CronSpec(
        minute=frozenset(minute),
        hour=frozenset(hour),
        day=frozenset(day),
        month=frozenset(month),
        weekday=frozenset(weekday),
        day_restricted=parts[2].strip() != "*",
        weekday_restricted=parts[4].strip() != "*",
        source=expr.strip(),
    )


def _day_matches(spec: CronSpec, when: datetime) -> bool:
    """Whether the date part of ``when`` satisfies day-of-month / weekday."""
    dom_ok = when.day in spec.day
    # Python: Mon=0..Sun=6; cron: Sun=0..Sat=6.
    dow = (when.weekday() + 1) % 7
    dow_ok = dow in spec.weekday
    if spec.day_restricted and spec.weekday_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def next_run_after(
    spec: CronSpec | str,
    after: datetime,
    *,
    max_years: int = 4,
) -> datetime:
    """Return the first matching local datetime strictly after ``after``.

    Raises ``ValueError`` when no occurrence exists within ``max_years``
    (e.g. ``0 0 30 2 *`` — Feb 30 never happens).
    """
    parsed = parse_cron(spec) if isinstance(spec, str) else spec
    start = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    hours = sorted(parsed.hour)
    minutes = sorted(parsed.minute)
    try:
        limit = start.replace(year=start.year + max_years)
    except ValueError:  # Feb 29 → clamp to Feb 28
        limit = start.replace(year=start.year + max_years, day=28)

    day_cursor = start.replace(hour=0, minute=0)
    while day_cursor < limit:
        if day_cursor.month in parsed.month and _day_matches(parsed, day_cursor):
            for hour in hours:
                for minute in minutes:
                    candidate = day_cursor.replace(hour=hour, minute=minute)
                    if candidate >= start:
                        return candidate
        day_cursor += timedelta(days=1)
    raise ValueError(f"未来 {max_years} 年内没有匹配的时间: {parsed.source!r}")


def validate_cron(expr: str) -> str:
    """Return the trimmed expression when valid; raise ``ValueError`` otherwise."""
    parse_cron(expr)
    return expr.strip()


__all__ = ["CronSpec", "next_run_after", "parse_cron", "validate_cron"]