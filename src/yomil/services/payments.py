"""Payment (occurrence) use cases: the main list, reconciling, skipping, and corrections."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from yomil.core.errors import InvalidStateError
from yomil.core.main_list import build_main_list
from yomil.core.models import Action, Entity, OccurrenceStatus
from yomil.core.recurrence import apply_weekend_policy
from yomil.core.validation import validate_amount
from yomil.services import settings
from yomil.services._audit import diff, utc_now
from yomil.services._materialize import materialize_series
from yomil.storage import event_log
from yomil.storage import occurrences as occ_repo
from yomil.storage import series as series_repo
from yomil.storage.db import transaction

if TYPE_CHECKING:
    import sqlite3
    from datetime import date

    from yomil.core.main_list import BillRow
    from yomil.core.models import EventLogEntry, Occurrence, Series


def materialize(conn: sqlite3.Connection, today: date, *, now: datetime | None = None) -> int:
    """Create any payments the active bills are missing as of ``today``. Safe to repeat.

    Call this before :func:`main_list` at startup, at midnight, and when the window is shown.
    Returns how many payments were created.
    """
    now = now or utc_now()
    with transaction(conn):
        return sum(
            materialize_series(conn, s, today, now)
            for s in series_repo.list_all(conn, active_only=True)
        )


def main_list(conn: sqlite3.Connection, today: date) -> list[BillRow]:
    """One row per active bill: its oldest unresolved payment. Read-only."""
    return build_main_list(
        occ_repo.unresolved_for_active_series(conn), today, settings.upcoming_threshold_days(conn)
    )


def get(conn: sqlite3.Connection, occurrence_id: int) -> Occurrence:
    return occ_repo.get(conn, occurrence_id)


def for_bill(conn: sqlite3.Connection, series_id: int) -> list[Occurrence]:
    """All of one bill's payments, oldest first. Read-only."""
    return occ_repo.for_series(conn, series_id)


def history(conn: sqlite3.Connection) -> list[Occurrence]:
    """Paid and skipped payments, newest first. Read-only."""
    return occ_repo.resolved(conn)


def change_history(conn: sqlite3.Connection, occurrence_id: int) -> list[EventLogEntry]:
    """The audit trail for one payment, oldest first. Read-only."""
    return event_log.for_entity(conn, Entity.OCCURRENCE, occurrence_id)


def update_pending(
    conn: sqlite3.Connection,
    occurrence_id: int,
    *,
    due_date: date,
    note: str | None,
    now: datetime | None = None,
) -> Occurrence:
    """Save a pending payment's due date and note without paying it.

    Moving the due date away from the schedule marks it overridden, so later bill edits
    leave it alone; moving it back to the scheduled date clears that again.
    """
    now = now or utc_now()
    with transaction(conn):
        old = _get_pending(conn, occurrence_id)
        series = series_repo.get(conn, old.series_id)
        new = replace(_moved(old, series, due_date), note=_clean(note))
        return _save(conn, old, new, Action.UPDATE, now)


def reconcile(
    conn: sqlite3.Connection,
    occurrence_id: int,
    *,
    paid_date: date,
    actual_amount_cents: int,
    note: str | None,
    today: date,
    due_date: date | None = None,
    now: datetime | None = None,
) -> Occurrence:
    """Mark a pending payment paid. Snapshots the bill's name for the history.

    The time of day it was paid is taken to be now (local), even if ``paid_date`` isn't
    today, so payments recorded on the same day sort in the order they were recorded.
    ``due_date``, if given, is saved along with it, as :func:`update_pending` would.
    """
    validate_amount(actual_amount_cents, required=True)
    now = now or utc_now()
    with transaction(conn):
        old = _get_pending(conn, occurrence_id)
        series = series_repo.get(conn, old.series_id)
        new = replace(
            _moved(old, series, due_date),
            status=OccurrenceStatus.PAID,
            payee_snapshot=series.payee,
            paid_at=_at_local_time_of(paid_date, now),
            actual_amount_cents=actual_amount_cents,
            note=_clean(note),
            reconciled_at=now,
        )
        saved = _save(conn, old, new, Action.RECONCILE, now)
        materialize_series(conn, series, today, now)  # paid ahead? bring up the next one
        return saved


def skip(
    conn: sqlite3.Connection,
    occurrence_id: int,
    *,
    note: str | None,
    today: date,
    due_date: date | None = None,
    now: datetime | None = None,
) -> Occurrence:
    """Dismiss a pending payment that doesn't need paying. ``due_date`` as for :func:`reconcile`."""
    now = now or utc_now()
    with transaction(conn):
        old = _get_pending(conn, occurrence_id)
        series = series_repo.get(conn, old.series_id)
        new = replace(
            _moved(old, series, due_date),
            status=OccurrenceStatus.SKIPPED,
            payee_snapshot=series.payee,
            note=_clean(note),
            reconciled_at=now,
        )
        saved = _save(conn, old, new, Action.SKIP, now)
        materialize_series(conn, series, today, now)
        return saved


def unreconcile(
    conn: sqlite3.Connection, occurrence_id: int, *, now: datetime | None = None
) -> Occurrence:
    """Undo a Mark Paid or Skip: the payment goes back to pending. Its note is kept."""
    now = now or utc_now()
    with transaction(conn):
        old = occ_repo.get(conn, occurrence_id)
        if not old.resolved:
            raise InvalidStateError("That payment is not marked paid or skipped.")
        new = replace(
            old,
            status=OccurrenceStatus.UPCOMING,
            payee_snapshot=None,
            paid_at=None,
            actual_amount_cents=None,
            reconciled_at=None,
        )
        return _save(conn, old, new, Action.UNRECONCILE, now)


def edit_reconciled(
    conn: sqlite3.Connection,
    occurrence_id: int,
    *,
    paid_date: date,
    actual_amount_cents: int,
    note: str | None,
    now: datetime | None = None,
) -> Occurrence:
    """Correct a paid payment's date, amount, or note. The time of day it was paid is kept."""
    validate_amount(actual_amount_cents, required=True)
    now = now or utc_now()
    with transaction(conn):
        old = occ_repo.get(conn, occurrence_id)
        if old.status is not OccurrenceStatus.PAID:
            raise InvalidStateError("Only paid payments can be edited this way.")
        assert old.paid_at is not None
        new = replace(
            old,
            paid_at=datetime.combine(paid_date, old.paid_at.time()),
            actual_amount_cents=actual_amount_cents,
            note=_clean(note),
        )
        return _save(conn, old, new, Action.EDIT_RECONCILED, now)


def _get_pending(conn: sqlite3.Connection, occurrence_id: int) -> Occurrence:
    occ = occ_repo.get(conn, occurrence_id)
    if occ.resolved:
        raise InvalidStateError(f"That payment is already {occ.status.value}.")
    return occ


def _moved(occ: Occurrence, series: Series, due_date: date | None) -> Occurrence:
    """``occ`` with a new due date (if any). Moving it off the schedule marks it overridden."""
    if due_date is None:
        return occ
    scheduled = apply_weekend_policy(occ.nominal_date, series.weekend_policy)
    return replace(occ, due_date=due_date, due_date_overridden=due_date != scheduled)


def _save(
    conn: sqlite3.Connection, old: Occurrence, new: Occurrence, action: Action, now: datetime
) -> Occurrence:
    assert new.id is not None
    occ_repo.update(conn, new)
    event_log.append(conn, Entity.OCCURRENCE, new.id, action, diff(old, new), now)
    return new


def _at_local_time_of(day: date, now: datetime) -> datetime:
    """``day`` at the local wall-clock time of ``now`` (to the second), as a naive datetime."""
    return datetime.combine(day, now.astimezone().time().replace(microsecond=0))


def _clean(note: str | None) -> str | None:
    """Blank notes are stored as NULL."""
    if note is None or not note.strip():
        return None
    return note.strip()
