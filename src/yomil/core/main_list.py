"""The main window's list: one row per active bill. Pure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from yomil.core.urgency import Urgency, classify

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date

    from yomil.core.models import Occurrence, Series


@dataclass(frozen=True, slots=True)
class BillRow:
    series: Series
    occurrence: Occurrence  # the bill's oldest unresolved payment
    urgency: Urgency
    more_overdue: int  # other overdue payments for this bill, shown as "(+N more overdue)"


def build_main_list(
    unresolved: Iterable[tuple[Series, Occurrence]], today: date, threshold_days: int
) -> list[BillRow]:
    """Rows for the bills in ``unresolved``, sorted by due date, then bill name."""
    by_series: dict[int, tuple[Series, list[Occurrence]]] = {}
    for series, occ in unresolved:
        assert series.id is not None
        by_series.setdefault(series.id, (series, []))[1].append(occ)
    rows = []
    for series, occs in by_series.values():
        oldest = min(occs, key=lambda o: o.nominal_date)
        more = sum(1 for o in occs if o is not oldest and o.due_date < today)
        rows.append(
            BillRow(
                series=series,
                occurrence=oldest,
                urgency=classify(oldest.due_date, today, threshold_days),
                more_overdue=more,
            )
        )
    rows.sort(key=lambda r: (r.occurrence.due_date, r.series.payee.casefold(), r.series.id))
    return rows
