"""Domain types.

Conventions:
* Money is integer cents (never floats).
* Dates are naive local calendar dates: a bill due on the 15th is due on the 15th
  wherever the machine is. Timestamps (``datetime``) appear only on audit records.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime


class AmountKind(enum.StrEnum):
    FIXED = "fixed"
    ESTIMATED = "estimated"
    VARIABLE = "variable"


class WeekendPolicy(enum.StrEnum):
    """How a nominal due date that lands on a weekend is displayed."""

    NONE = "none"
    PREVIOUS_BUSINESS_DAY = "previous"
    NEXT_BUSINESS_DAY = "next"


class OccurrenceStatus(enum.StrEnum):
    UPCOMING = "upcoming"
    PAID = "paid"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Series:
    """A recurring bill definition (the template)."""

    id: int | None
    payee: str
    rrule: str
    dtstart: date
    amount_kind: AmountKind = AmountKind.FIXED
    expected_amount_cents: int | None = None
    until: date | None = None
    weekend_policy: WeekendPolicy = WeekendPolicy.NONE
    lead_days: tuple[int, ...] = (7, 3, 0)
    autopay: bool = False
    category: str | None = None
    url: str | None = None
    notes: str | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One due instance of a series."""

    id: int | None
    series_id: int
    nominal_date: date  # the date the recurrence rule produced; never adjusted
    due_date: date  # nominal date after weekend adjustment; what the user sees
    expected_amount_cents: int | None
    status: OccurrenceStatus = OccurrenceStatus.UPCOMING
    # Filled in when reconciled. Snapshotted so later series edits can't rewrite history.
    payee_snapshot: str | None = None
    paid_date: date | None = None
    actual_amount_cents: int | None = None
    note: str | None = None
    reconciled_at: datetime | None = None
