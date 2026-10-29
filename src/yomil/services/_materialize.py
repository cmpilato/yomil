"""Materialization steps shared by the bill and payment services. Callers own the transaction."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from yomil.core.models import Action, Entity
from yomil.core.planning import plan_materialization
from yomil.services._audit import jsonable
from yomil.storage import event_log
from yomil.storage import occurrences as occ_repo
from yomil.storage import series as series_repo

if TYPE_CHECKING:
    import sqlite3
    from datetime import date, datetime

    from yomil.core.models import Series


def materialize_series(
    conn: sqlite3.Connection,
    series: Series,
    today: date,
    now: datetime,
    *,
    restart: bool = False,
) -> int:
    """Create (and log) any occurrences ``series`` is missing. Returns how many.

    With ``restart``, dates before today that the series never had are not back-filled
    (after a schedule edit or reactivation). See :mod:`yomil.core.planning`.
    """
    assert conn.in_transaction
    assert series.id is not None
    floor = series_repo.get_materialized_through(conn, series.id)
    if restart:
        yesterday = today - timedelta(days=1)
        floor = yesterday if floor is None else max(floor, yesterday)
    created = 0
    existing = occ_repo.for_series(conn, series.id)
    for occ in plan_materialization(series, existing, today, floor=floor):
        new_id = occ_repo.insert_if_missing(conn, occ)
        if new_id is None:
            continue
        created += 1
        event_log.append(
            conn,
            Entity.OCCURRENCE,
            new_id,
            Action.CREATE,
            {
                "series_id": series.id,
                "nominal_date": jsonable(occ.nominal_date),
                "due_date": jsonable(occ.due_date),
                "expected_amount_cents": occ.expected_amount_cents,
            },
            now,
        )
    if series.active and (floor is None or floor < today):
        series_repo.set_materialized_through(conn, series.id, today)
    return created
