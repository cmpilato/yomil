"""Decide which occurrence rows should exist for a series. Pure: the caller does the I/O.

Materialization rule: an active series has a row for every instance from ``dtstart``
through today, and then for each following instance up to and including the first one
that is still unresolved. Normally that is just "the next one after today", but if the user
pays ahead, the next instance after that appears, so a bill never vanishes from the
main list while its schedule continues.

Materialization only ever moves *forward*: the caller remembers how far it has got
(``floor``) and nothing on or before that date is ever created again. After a schedule
edit or reactivating a retired bill, the floor jumps to yesterday, so neither one
conjures a flood of overdue payments for dates the bill never had.

Series-edit rule: when the schedule or amount changes, only *future, pending,
not-overridden* rows are touched. Overdue, hand-moved, and resolved rows are left alone.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from typing import TYPE_CHECKING

from yomil.core.models import Occurrence, OccurrenceStatus
from yomil.core.recurrence import apply_weekend_policy, expand, next_after

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date

    from yomil.core.models import Series


def new_occurrence(series: Series, nominal: date) -> Occurrence:
    """An unsaved pending occurrence of ``series`` for ``nominal``."""
    assert series.id is not None
    return Occurrence(
        id=None,
        series_id=series.id,
        nominal_date=nominal,
        due_date=apply_weekend_policy(nominal, series.weekend_policy),
        expected_amount_cents=series.expected_amount_cents,
    )


def plan_materialization(
    series: Series, existing: Iterable[Occurrence], today: date, *, floor: date | None = None
) -> list[Occurrence]:
    """Occurrences missing from ``existing`` under the materialization rule.

    Instances on or before ``floor`` (if given) are not created, except as the
    "next one after today".
    """
    if not series.active:
        return []
    by_nominal = {o.nominal_date: o for o in existing}
    start = series.dtstart if floor is None else max(series.dtstart, floor + timedelta(days=1))
    wanted = expand(series.rrule, series.dtstart, start, today, until=series.until)
    cursor = today
    while (
        nominal := next_after(series.rrule, series.dtstart, cursor, until=series.until)
    ) is not None:
        wanted.append(nominal)
        have = by_nominal.get(nominal)
        if have is None or not have.resolved:
            break
        cursor = nominal
    return [new_occurrence(series, d) for d in wanted if d not in by_nominal]


def is_regenerable(occ: Occurrence, today: date) -> bool:
    """Whether a series edit may move, re-price, or remove ``occ``."""
    return (
        occ.status is OccurrenceStatus.UPCOMING
        and not occ.due_date_overridden
        and occ.due_date >= today
    )


@dataclass(frozen=True, slots=True)
class Regeneration:
    """Changes a series edit makes to existing rows (new rows come from materialization)."""

    delete: list[Occurrence]
    update: list[Occurrence]  # with new values; same ids


def plan_regeneration(series: Series, existing: Iterable[Occurrence], today: date) -> Regeneration:
    """Bring regenerable rows in line with an edited ``series``.

    Rows whose nominal date the new schedule still produces are updated in place (so a
    note left on them survives); the rest are deleted.
    """
    candidates = sorted(
        (o for o in existing if is_regenerable(o, today)), key=lambda o: o.nominal_date
    )
    if not candidates:
        return Regeneration(delete=[], update=[])
    still_scheduled: set[date] = set()
    if series.active:
        still_scheduled.update(
            expand(
                series.rrule,
                series.dtstart,
                candidates[0].nominal_date,
                candidates[-1].nominal_date,
                until=series.until,
            )
        )
    delete: list[Occurrence] = []
    update: list[Occurrence] = []
    for occ in candidates:
        if occ.nominal_date not in still_scheduled:
            delete.append(occ)
            continue
        fresh = new_occurrence(series, occ.nominal_date)
        changed = replace(
            occ, due_date=fresh.due_date, expected_amount_cents=fresh.expected_amount_cents
        )
        if changed != occ:
            update.append(changed)
    return Regeneration(delete=delete, update=update)
