"""Repository functions for the ``occurrence`` table. No transactions or audit logging here."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from yomil.core.errors import NotFoundError
from yomil.core.models import Occurrence, OccurrenceStatus
from yomil.storage import series as series_repo
from yomil.storage._convert import (
    local_timestamp_or_none,
    parse_timestamp_or_none,
    timestamp_or_none,
)

if TYPE_CHECKING:
    import sqlite3

    from yomil.core.models import Series

# Columns a row can change after creation (series_id and nominal_date are its identity).
_MUTABLE = (
    "due_date",
    "expected_amount_cents",
    "status",
    "due_date_overridden",
    "payee_snapshot",
    "paid_at",
    "actual_amount_cents",
    "note",
    "reconciled_at",
)


def _mutable_params(o: Occurrence) -> tuple[object, ...]:
    return (
        o.due_date.isoformat(),
        o.expected_amount_cents,
        o.status.value,
        int(o.due_date_overridden),
        o.payee_snapshot,
        local_timestamp_or_none(o.paid_at),
        o.actual_amount_cents,
        o.note,
        timestamp_or_none(o.reconciled_at),
    )


def from_row(row: sqlite3.Row) -> Occurrence:
    return Occurrence(
        id=row["id"],
        series_id=row["series_id"],
        nominal_date=date.fromisoformat(row["nominal_date"]),
        due_date=date.fromisoformat(row["due_date"]),
        expected_amount_cents=row["expected_amount_cents"],
        status=OccurrenceStatus(row["status"]),
        due_date_overridden=bool(row["due_date_overridden"]),
        payee_snapshot=row["payee_snapshot"],
        paid_at=None if row["paid_at"] is None else datetime.fromisoformat(row["paid_at"]),
        actual_amount_cents=row["actual_amount_cents"],
        note=row["note"],
        reconciled_at=parse_timestamp_or_none(row["reconciled_at"]),
    )


def insert_if_missing(conn: sqlite3.Connection, o: Occurrence) -> int | None:
    """Insert ``o`` unless its (series, nominal date) exists. Returns the new id, if any."""
    columns = ", ".join(("series_id", "nominal_date", *_MUTABLE))
    placeholders = ", ".join("?" * (2 + len(_MUTABLE)))
    cur = conn.execute(
        f"INSERT OR IGNORE INTO occurrence ({columns}) VALUES ({placeholders})",
        (o.series_id, o.nominal_date.isoformat(), *_mutable_params(o)),
    )
    return cur.lastrowid if cur.rowcount == 1 else None


def update(conn: sqlite3.Connection, o: Occurrence) -> None:
    assert o.id is not None
    assignments = ", ".join(f"{c} = ?" for c in _MUTABLE)
    cur = conn.execute(
        f"UPDATE occurrence SET {assignments} WHERE id = ?", (*_mutable_params(o), o.id)
    )
    if cur.rowcount == 0:
        raise NotFoundError(f"payment {o.id} not found")


def delete(conn: sqlite3.Connection, occurrence_id: int) -> None:
    cur = conn.execute("DELETE FROM occurrence WHERE id = ?", (occurrence_id,))
    if cur.rowcount == 0:
        raise NotFoundError(f"payment {occurrence_id} not found")


def get(conn: sqlite3.Connection, occurrence_id: int) -> Occurrence:
    row = conn.execute("SELECT * FROM occurrence WHERE id = ?", (occurrence_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"payment {occurrence_id} not found")
    return from_row(row)


def for_series(conn: sqlite3.Connection, series_id: int) -> list[Occurrence]:
    rows = conn.execute(
        "SELECT * FROM occurrence WHERE series_id = ? ORDER BY nominal_date", (series_id,)
    )
    return [from_row(r) for r in rows]


def unresolved_for_active_series(conn: sqlite3.Connection) -> list[tuple[Series, Occurrence]]:
    rows = conn.execute(
        "SELECT o.* FROM occurrence o JOIN series s ON s.id = o.series_id"
        " WHERE o.status = 'upcoming' AND s.active = 1 ORDER BY o.due_date, o.id"
    ).fetchall()
    series = {s.id: s for s in series_repo.list_all(conn, active_only=True)}
    return [(series[r["series_id"]], from_row(r)) for r in rows]


def resolved(conn: sqlite3.Connection) -> list[Occurrence]:
    """Paid and skipped occurrences, newest first (by paid time, or due date if skipped)."""
    rows = conn.execute(
        "SELECT * FROM occurrence WHERE status <> 'upcoming'"
        " ORDER BY COALESCE(paid_at, due_date) DESC, id DESC"
    )
    return [from_row(r) for r in rows]
