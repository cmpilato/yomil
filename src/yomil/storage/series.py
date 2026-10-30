"""Repository functions for the ``series`` table. No transactions or audit logging here."""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING

from yomil.core.errors import NotFoundError
from yomil.core.models import AmountKind, Series, WeekendPolicy
from yomil.storage._convert import date_or_none, iso_or_none, timestamp

if TYPE_CHECKING:
    import sqlite3
    from datetime import datetime

_COLUMNS = (
    "payee, category, amount_kind, expected_amount_cents, rrule, dtstart, until,"
    " weekend_policy, lead_days_json, autopay, url, notes, active"
)


def _params(s: Series) -> tuple[object, ...]:
    return (
        s.payee,
        s.category,
        s.amount_kind.value,
        s.expected_amount_cents,
        s.rrule,
        s.dtstart.isoformat(),
        iso_or_none(s.until),
        s.weekend_policy.value,
        json.dumps(list(s.lead_days)),
        int(s.autopay),
        s.url,
        s.notes,
        int(s.active),
    )


def from_row(row: sqlite3.Row) -> Series:
    return Series(
        id=row["id"],
        payee=row["payee"],
        rrule=row["rrule"],
        dtstart=date.fromisoformat(row["dtstart"]),
        amount_kind=AmountKind(row["amount_kind"]),
        expected_amount_cents=row["expected_amount_cents"],
        until=date_or_none(row["until"]),
        weekend_policy=WeekendPolicy(row["weekend_policy"]),
        lead_days=tuple(json.loads(row["lead_days_json"])),
        autopay=bool(row["autopay"]),
        category=row["category"],
        url=row["url"],
        notes=row["notes"],
        active=bool(row["active"]),
    )


def insert(conn: sqlite3.Connection, s: Series, now: datetime) -> int:
    """Insert ``s`` (whose ``id`` is ignored) and return the new id."""
    ts = timestamp(now)
    cur = conn.execute(
        f"INSERT INTO series ({_COLUMNS}, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (*_params(s), ts, ts),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def update(conn: sqlite3.Connection, s: Series, now: datetime) -> None:
    assert s.id is not None
    assignments = ", ".join(f"{c.strip()} = ?" for c in _COLUMNS.split(","))
    cur = conn.execute(
        f"UPDATE series SET {assignments}, updated_at = ? WHERE id = ?",
        (*_params(s), timestamp(now), s.id),
    )
    if cur.rowcount == 0:
        raise NotFoundError(f"bill {s.id} not found")


def get(conn: sqlite3.Connection, series_id: int) -> Series:
    row = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"bill {series_id} not found")
    return from_row(row)


def list_all(conn: sqlite3.Connection, *, active_only: bool = False) -> list[Series]:
    """Active bills first, then by name."""
    where = "WHERE active = 1" if active_only else ""
    rows = conn.execute(
        f"SELECT * FROM series {where} ORDER BY active DESC, payee COLLATE NOCASE, id"
    )
    return [from_row(r) for r in rows]


def delete(conn: sqlite3.Connection, series_id: int) -> None:
    cur = conn.execute("DELETE FROM series WHERE id = ?", (series_id,))
    if cur.rowcount == 0:
        raise NotFoundError(f"bill {series_id} not found")


def get_materialized_through(conn: sqlite3.Connection, series_id: int) -> date | None:
    """The last "today" this series' occurrences were created through, if any."""
    row = conn.execute(
        "SELECT materialized_through FROM series WHERE id = ?", (series_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"bill {series_id} not found")
    return date_or_none(row["materialized_through"])


def set_materialized_through(conn: sqlite3.Connection, series_id: int, through: date) -> None:
    conn.execute(
        "UPDATE series SET materialized_through = ? WHERE id = ?",
        (through.isoformat(), series_id),
    )
