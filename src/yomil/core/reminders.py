"""Which reminder notifications are due, and what they say. Pure.

Each bill's reminders are about its oldest unresolved payment (the one on the main
list). A payment's reminder is identified by a *key*:

* a lead day (``7``, ``3``, ``0``...): the most specific of the bill's ``lead_days``
  that has been reached, so if the PC was off for a few days, only the most urgent
  reminder is sent rather than a backlog of stale ones;
* minus the days overdue (``-1``, ``-2``...): a fresh key each day, so overdue bills
  are mentioned once a day until resolved.

A bill with no ``lead_days`` gets no reminders at all, overdue or not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import TYPE_CHECKING

from yomil.core.formatting import USD, format_date, format_money
from yomil.core.models import AmountKind

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence
    from datetime import date

    from yomil.core.formatting import MoneyFormat
    from yomil.core.main_list import BillRow

# (days before the due date, checkbox label), as offered in the bill editor.
LEAD_DAY_CHOICES = (
    (14, "2 weeks before"),
    (7, "1 week before"),
    (3, "3 days before"),
    (1, "1 day before"),
    (0, "On the due date"),
)

COMBINE_AT = 3  # this many reminders at once become a single notice

# No notifications overnight: anything due waits for the morning.
QUIET_FROM = time(21, 0)
QUIET_UNTIL = time(8, 0)


@dataclass(frozen=True, slots=True)
class Reminder:
    series_id: int
    occurrence_id: int
    key: int  # a lead day, or minus the days overdue
    payee: str
    text: str  # "Due in 3 days (Sun Nov 1, 2026). About $120.00."


@dataclass(frozen=True, slots=True)
class Notice:
    """One notification on screen, covering one or more reminders."""

    title: str
    body: str
    series_id: int | None  # the bill to show when it's clicked (None: just the list)
    reminders: tuple[Reminder, ...]


def reminder_key(lead_days: Iterable[int], due: date, today: date) -> int | None:
    """The key a payment due on ``due`` has reached by ``today``, if any."""
    lead_days = tuple(lead_days)
    if not lead_days:
        return None
    days_left = (due - today).days
    if days_left < 0:
        return days_left
    reached = [d for d in lead_days if days_left <= d]
    return min(reached) if reached else None


def due_reminders(
    rows: Iterable[BillRow],
    today: date,
    sent: Collection[tuple[int, int]],
    fmt: MoneyFormat = USD,
) -> list[Reminder]:
    """Reminders for ``rows`` (main-list rows) not yet in ``sent`` ((occurrence, key))."""
    reminders = []
    for row in rows:
        occ, series = row.occurrence, row.series
        assert occ.id is not None
        assert series.id is not None
        key = reminder_key(series.lead_days, occ.due_date, today)
        if key is None or (occ.id, key) in sent:
            continue
        reminders.append(
            Reminder(series.id, occ.id, key, series.payee, _reminder_text(row, today, fmt))
        )
    return reminders


def _reminder_text(row: BillRow, today: date, fmt: MoneyFormat) -> str:
    due = row.occurrence.due_date
    days = (due - today).days
    if days < 0:
        n = -days
        text = f"Overdue by {n} {'day' if n == 1 else 'days'} (was due {format_date(due)})."
        if row.more_overdue:
            m = row.more_overdue
            text += f" {m} more {'payment' if m == 1 else 'payments'} also overdue."
    elif days == 0:
        text = "Due today."
    elif days == 1:
        text = f"Due tomorrow ({format_date(due)})."
    else:
        text = f"Due in {days} days ({format_date(due)})."
    cents = row.occurrence.expected_amount_cents
    if cents is not None and row.series.amount_kind is not AmountKind.VARIABLE:
        about = "About " if row.series.amount_kind is AmountKind.ESTIMATED else ""
        text += f" {about}{format_money(cents, fmt)}."
    return text


def notices(reminders: Sequence[Reminder]) -> list[Notice]:
    """What to put on screen: one notice per reminder, or one for all if there are many."""
    if len(reminders) < COMBINE_AT:
        return [Notice(r.payee, r.text, r.series_id, (r,)) for r in reminders]
    names = [r.payee for r in reminders]
    overdue = sum(1 for r in reminders if r.key < 0)
    body = f"{', '.join(names[:2])}, and {len(names) - 2} more."
    if overdue:
        body += f" {overdue} {'is' if overdue == 1 else 'are'} overdue."
    return [Notice(f"{len(reminders)} bills need attention", body, None, tuple(reminders))]


def in_quiet_hours(now: time) -> bool:
    return now >= QUIET_FROM or now < QUIET_UNTIL


def quiet_hours_text() -> str:
    return (
        "Reminders wait until morning: none between "
        f"{_clock(QUIET_FROM)} and {_clock(QUIET_UNTIL)}."
    )


def _clock(t: time) -> str:
    hour = t.hour % 12 or 12
    minutes = f":{t.minute:02d}" if t.minute else ""
    return f"{hour}{minutes} {'AM' if t.hour < 12 else 'PM'}"


def merge_lead_days(checked: Iterable[int], original: Iterable[int]) -> tuple[int, ...]:
    """The checked choices, plus any of ``original``'s days the checkboxes don't offer
    (set up outside YOMIL), which are kept rather than silently dropped."""
    offered = {d for d, _ in LEAD_DAY_CHOICES}
    days = set(checked) | {d for d in original if d not in offered}
    return tuple(sorted(days, reverse=True))
