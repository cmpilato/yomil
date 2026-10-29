from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from yomil.core.errors import NotFoundError
from yomil.core.models import (
    Action,
    AmountKind,
    Entity,
    Occurrence,
    OccurrenceStatus,
    WeekendPolicy,
)
from yomil.storage import event_log, settings
from yomil.storage import occurrences as occ_repo
from yomil.storage import series as series_repo

from ..conftest import NOW, make_series

if TYPE_CHECKING:
    import sqlite3


def test_series_round_trip(conn: sqlite3.Connection) -> None:
    s = make_series(
        amount_kind=AmountKind.ESTIMATED,
        until=date(2027, 1, 1),
        weekend_policy=WeekendPolicy.PREVIOUS_BUSINESS_DAY,
        lead_days=(5, 1),
        autopay=True,
        category="Utilities",
        url="https://example.com",
        notes="hi",
    )
    sid = series_repo.insert(conn, s, NOW)
    assert series_repo.get(conn, sid) == replace(s, id=sid)

    edited = replace(s, id=sid, payee="Power Co", active=False)
    series_repo.update(conn, edited, NOW)
    assert series_repo.get(conn, sid) == edited


def test_series_list_puts_active_first_then_name(conn: sqlite3.Connection) -> None:
    for payee, active in (("b", True), ("A", False), ("c", True), ("a", True)):
        series_repo.insert(conn, make_series(payee=payee, active=active), NOW)
    assert [s.payee for s in series_repo.list_all(conn)] == ["a", "b", "c", "A"]
    assert [s.payee for s in series_repo.list_all(conn, active_only=True)] == ["a", "b", "c"]


def test_series_missing(conn: sqlite3.Connection) -> None:
    with pytest.raises(NotFoundError):
        series_repo.get(conn, 42)
    with pytest.raises(NotFoundError):
        series_repo.update(conn, make_series(id=42), NOW)
    with pytest.raises(NotFoundError):
        series_repo.delete(conn, 42)


def test_occurrence_round_trip_and_insert_if_missing(conn: sqlite3.Connection) -> None:
    sid = series_repo.insert(conn, make_series(), NOW)
    occ = Occurrence(
        id=None,
        series_id=sid,
        nominal_date=date(2026, 2, 15),
        due_date=date(2026, 2, 16),
        expected_amount_cents=500,
    )
    oid = occ_repo.insert_if_missing(conn, occ)
    assert oid is not None
    assert occ_repo.insert_if_missing(conn, occ) is None
    assert occ_repo.get(conn, oid) == replace(occ, id=oid)

    paid = replace(
        occ,
        id=oid,
        status=OccurrenceStatus.PAID,
        due_date_overridden=True,
        payee_snapshot="Electric",
        paid_date=date(2026, 2, 14),
        actual_amount_cents=512,
        note="n",
        reconciled_at=datetime(2026, 2, 14, 9, 30, tzinfo=UTC),
    )
    occ_repo.update(conn, paid)
    assert occ_repo.get(conn, oid) == paid
    assert occ_repo.resolved(conn) == [paid]
    assert occ_repo.unresolved_for_active_series(conn) == []


def test_occurrence_missing(conn: sqlite3.Connection) -> None:
    with pytest.raises(NotFoundError):
        occ_repo.get(conn, 42)
    with pytest.raises(NotFoundError):
        occ_repo.delete(conn, 42)


def test_settings(conn: sqlite3.Connection) -> None:
    assert settings.get(conn, "x") is None
    settings.put(conn, "x", "1")
    settings.put(conn, "x", "2")
    assert settings.get(conn, "x") == "2"


def test_event_log_round_trip(conn: sqlite3.Connection) -> None:
    event_log.append(conn, Entity.SERIES, 7, Action.CREATE, {"a": [1, "b"]}, NOW)
    event_log.append(conn, Entity.SERIES, 8, Action.CREATE, {}, NOW)
    [entry] = event_log.for_entity(conn, Entity.SERIES, 7)
    assert (entry.at, entry.entity, entry.entity_id, entry.action, entry.detail) == (
        NOW,
        Entity.SERIES,
        7,
        Action.CREATE,
        {"a": [1, "b"]},
    )


def test_naive_timestamps_are_refused(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        event_log.append(conn, Entity.SERIES, 1, Action.CREATE, {}, datetime(2026, 1, 1))  # noqa: DTZ001
