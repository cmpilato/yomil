"""Friendly schedules ("Every month") and the RRULEs behind them. Pure.

A schedule is just *how often*. *Which* day comes from the bill's first due date: a
monthly bill first due on the 15th is due on the 15th, a weekly one first due on a
Tuesday is due on Tuesdays. So the first due date is always a real occurrence of the
rule (dateutil silently drops a ``dtstart`` that doesn't match its rule).

Rules this module didn't write show up as :attr:`Repeat.CUSTOM` and are kept as they are.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

from dateutil.rrule import rrulestr

from yomil.core.recurrence import apply_weekend_policy, monthly_on_day

if TYPE_CHECKING:
    from yomil.core.models import Series

_FEB_29_YEARLY = ";BYMONTH=2;BYMONTHDAY=28,29;BYSETPOS=-1"  # Feb 28 in common years


class Repeat(enum.StrEnum):
    ONCE = "once"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class Schedule:
    repeat: Repeat
    interval: int = 1  # every N weeks/months/years; ignored for ONCE and CUSTOM
    # MONTHLY only, and rarely: a later day than the first due date's, when that date is
    # this day clamped to a short month (e.g. "the 31st", first due on April 30).
    month_day: int | None = None

    def day_of_month(self, first_due: date) -> int:
        return self.month_day or first_due.day

    def to_rrule(self, first_due: date) -> str:
        if self.repeat is Repeat.CUSTOM:
            msg = "a custom schedule has no rule of its own; keep the bill's existing one"
            raise ValueError(msg)
        if self.interval < 1:
            msg = f"interval must be >= 1, got {self.interval}"
            raise ValueError(msg)
        if self.repeat is Repeat.ONCE:
            return "FREQ=YEARLY;COUNT=1"
        if self.repeat is Repeat.WEEKLY:
            return f"FREQ=WEEKLY;INTERVAL={self.interval}"
        if self.repeat is Repeat.MONTHLY:
            return monthly_on_day(self.day_of_month(first_due), interval=self.interval)
        rule = f"FREQ=YEARLY;INTERVAL={self.interval}"
        return rule + _FEB_29_YEARLY if (first_due.month, first_due.day) == (2, 29) else rule


def parse_schedule(rule: str, first_due: date) -> Schedule:
    """The schedule that would write exactly ``rule``, or ``CUSTOM``."""
    match = re.search(r"(?:^|;)INTERVAL=(\d+)(?:;|$)", rule)
    interval = int(match.group(1)) if match else 1
    interval = max(interval, 1)
    candidates = [Schedule(Repeat.ONCE)] + [
        Schedule(repeat, interval) for repeat in (Repeat.WEEKLY, Repeat.MONTHLY, Repeat.YEARLY)
    ]
    if (first_due + timedelta(days=1)).day == 1:  # last day of its month: maybe clamped
        candidates += [
            Schedule(Repeat.MONTHLY, interval, day) for day in range(first_due.day + 1, 32)
        ]
    for candidate in candidates:
        if candidate.to_rrule(first_due) == rule:
            return candidate
    return Schedule(Repeat.CUSTOM)


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _every(interval: int, unit: str) -> str:
    return f"Every {unit}" if interval == 1 else f"Every {interval} {unit}s"


def describe(schedule: Schedule, first_due: date) -> str:
    """``"Every month on the 15th"``, ``"Every 2 weeks on Tuesday"``, ..."""
    n = schedule.interval
    if schedule.repeat is Repeat.ONCE:
        return "One time only"
    if schedule.repeat is Repeat.WEEKLY:
        return f"{_every(n, 'week')} on {first_due:%A}"
    if schedule.repeat is Repeat.MONTHLY:
        day = schedule.day_of_month(first_due)
        text = f"{_every(n, 'month')} on the {_ordinal(day)}"
        if day > 28:
            text += " (or the last day of shorter months)"
        return text
    if schedule.repeat is Repeat.YEARLY:
        text = f"{_every(n, 'year')} on {first_due:%B} {first_due.day}"
        if (first_due.month, first_due.day) == (2, 29):
            text += " (February 28 in other years)"
        return text
    return "Custom schedule"


@dataclass(frozen=True, slots=True)
class SchedulePreview:
    upcoming: list[date]  # the next due dates from today on, after weekend adjustment
    past: int  # how many due dates fall before today (overdue if the bill is new)


def preview(series: Series, today: date, count: int = 5) -> SchedulePreview:
    """What ``series``'s schedule will produce, to show before saving it."""
    rr = rrulestr(series.rrule, dtstart=datetime.combine(series.dtstart, time.min))
    upcoming: list[date] = []
    past = 0
    for dt in rr:
        nominal = dt.date()
        if series.until is not None and nominal > series.until:
            break
        due = apply_weekend_policy(nominal, series.weekend_policy)
        if due < today:
            past += 1
            if past > 10_000:  # a daily custom rule from long ago; stop counting
                break
            continue
        upcoming.append(due)
        if len(upcoming) == count:
            break
    return SchedulePreview(upcoming, past)
