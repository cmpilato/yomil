"""Recurrence expansion built on RFC 5545 RRULEs (via python-dateutil).

Design notes:
* Series are anchored on the *nominal* date. Weekend adjustment is applied afterwards,
  to the displayed due date only, so adjustments can never cause drift.
* Plain RRULE ``BYMONTHDAY=31`` *skips* short months. For bills, "the 31st" almost
  always means "the 31st, or the last day of shorter months", so use
  :func:`monthly_on_day` to build the rule.
* All functions are pure; "today" is always passed in by the caller.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from dateutil.rrule import rrulestr

from yomil.core.models import WeekendPolicy

_SATURDAY = 5  # date.weekday(): Monday == 0


def monthly_on_day(day: int, *, interval: int = 1) -> str:
    """RRULE for "every ``interval`` months on ``day``, clamped to month length"."""
    if not 1 <= day <= 31:
        msg = f"day must be in 1..31, got {day}"
        raise ValueError(msg)
    if interval < 1:
        msg = f"interval must be >= 1, got {interval}"
        raise ValueError(msg)
    base = f"FREQ=MONTHLY;INTERVAL={interval}"
    if day <= 28:
        return f"{base};BYMONTHDAY={day}"
    candidates = ",".join(str(d) for d in range(28, day + 1))
    return f"{base};BYMONTHDAY={candidates};BYSETPOS=-1"


def expand(
    rule: str,
    dtstart: date,
    window_start: date,
    window_end: date,
    *,
    until: date | None = None,
) -> list[date]:
    """Nominal dates of ``rule`` in ``[window_start, window_end]`` (inclusive)."""
    if window_end < window_start:
        return []
    rr = rrulestr(rule, dtstart=datetime.combine(dtstart, time.min))
    last = min(window_end, until) if until is not None else window_end
    if last < window_start:
        return []
    found = rr.between(
        datetime.combine(window_start, time.min),
        datetime.combine(last, time.min),
        inc=True,
    )
    return [dt.date() for dt in found]


def next_after(rule: str, dtstart: date, after: date, *, until: date | None = None) -> date | None:
    """First nominal date of ``rule`` strictly after ``after``, or None if the rule has ended."""
    rr = rrulestr(rule, dtstart=datetime.combine(dtstart, time.min))
    found = rr.after(datetime.combine(after, time.min), inc=False)
    if found is None:
        return None
    nominal = found.date()
    if until is not None and nominal > until:
        return None
    return nominal


def apply_weekend_policy(nominal: date, policy: WeekendPolicy) -> date:
    """Shift a weekend date to the adjacent business day per ``policy``."""
    if policy is WeekendPolicy.NONE or nominal.weekday() < _SATURDAY:
        return nominal
    if policy is WeekendPolicy.PREVIOUS_BUSINESS_DAY:
        return nominal - timedelta(days=nominal.weekday() - 4)
    return nominal + timedelta(days=7 - nominal.weekday())
