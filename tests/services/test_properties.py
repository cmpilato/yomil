"""Property tests for materialization and series-edit regeneration, through the services."""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from datetime import date, timedelta
from typing import TYPE_CHECKING

from hypothesis import given, settings
from hypothesis import strategies as st

from yomil.core.models import OccurrenceStatus, Series, WeekendPolicy
from yomil.core.planning import is_regenerable, new_occurrence
from yomil.core.recurrence import expand, monthly_on_day
from yomil.services import bills, payments

from ..conftest import NOW, open_db

if TYPE_CHECKING:
    import sqlite3

    from yomil.core.models import Occurrence

_START = date(2025, 1, 1)

rules = st.one_of(
    st.builds(lambda d, i: monthly_on_day(d, interval=i), st.integers(1, 31), st.integers(1, 3)),
    st.builds(lambda i: f"FREQ=WEEKLY;INTERVAL={i}", st.integers(1, 4)),
    st.just("FREQ=YEARLY"),
    st.just("FREQ=YEARLY;COUNT=1"),
    st.builds(lambda n: f"FREQ=MONTHLY;COUNT={n}", st.integers(1, 6)),
)
days = st.integers(0, 500).map(lambda n: _START + timedelta(days=n))


@st.composite
def series(draw: st.DrawFn) -> Series:
    dtstart = draw(days)
    until = draw(st.none() | st.integers(0, 400).map(lambda n: dtstart + timedelta(days=n)))
    return Series(
        id=None,
        payee="Bill",
        rrule=draw(rules),
        dtstart=dtstart,
        until=until,
        weekend_policy=draw(st.sampled_from(WeekendPolicy)),
        expected_amount_cents=draw(st.integers(0, 100_000)),
    )


def _rows(conn: sqlite3.Connection, s: Series) -> list[Occurrence]:
    assert s.id is not None
    return payments.for_bill(conn, s.id)


def _rule_continues_after(s: Series, today: date) -> bool:
    return bool(
        expand(s.rrule, s.dtstart, today + timedelta(days=1), date(2040, 1, 1), until=s.until)
    )


@settings(max_examples=150, deadline=None)
@given(s=series(), steps=st.lists(st.integers(0, 120), min_size=1, max_size=4))
def test_materialization_is_idempotent_and_complete(s: Series, steps: list[int]) -> None:
    with closing(open_db()) as conn:
        today = s.dtstart - timedelta(days=30)
        s = bills.create(conn, s, today=today, now=NOW)
        for step in steps:
            today += timedelta(days=step)
            payments.materialize(conn, today, now=NOW)
            assert not conn.in_transaction
            rows = _rows(conn, s)

            # Repeating is a no-op.
            assert payments.materialize(conn, today, now=NOW) == 0
            assert _rows(conn, s) == rows

            # Exactly the schedule's dates from dtstart through today, plus the next one.
            through_today = expand(s.rrule, s.dtstart, s.dtstart, today, until=s.until)
            nominals = [o.nominal_date for o in rows]
            assert nominals[: len(through_today)] == through_today
            extra = nominals[len(through_today) :]
            assert len(extra) == (1 if _rule_continues_after(s, today) else 0)
            assert all(o == new_occurrence(s, o.nominal_date) for o in _strip_ids(rows))


@settings(max_examples=150, deadline=None)
@given(
    s=series(),
    new_rule=rules,
    new_amount=st.integers(0, 100_000),
    new_policy=st.sampled_from(WeekendPolicy),
    offset=st.integers(-30, 400),
    actions=st.lists(st.sampled_from(["pay", "skip", "move", "none"]), max_size=12),
)
def test_series_edit_only_touches_future_pending_unmoved(
    s: Series,
    new_rule: str,
    new_amount: int,
    new_policy: WeekendPolicy,
    offset: int,
    actions: list[str],
) -> None:
    with closing(open_db()) as conn:
        today = s.dtstart + timedelta(days=offset)
        s = bills.create(conn, s, today=today, now=NOW)

        # Resolve or move some payments (oldest first), paying ahead when actions remain.
        for action in actions:
            pending = [o for o in _rows(conn, s) if not o.resolved]
            if not pending:
                break
            occ = pending[0]
            assert occ.id is not None
            if action == "pay":
                payments.reconcile(
                    conn, occ.id, paid_date=today, actual_amount_cents=1, note=None, today=today
                )
            elif action == "skip":
                payments.skip(conn, occ.id, note=None, today=today)
            elif action == "move":
                payments.update_pending(
                    conn, occ.id, due_date=occ.due_date + timedelta(days=3), note="moved"
                )

        before = {o.id: o for o in _rows(conn, s)}
        protected = {i: o for i, o in before.items() if not is_regenerable(o, today)}

        edited = replace(
            s, rrule=new_rule, expected_amount_cents=new_amount, weekend_policy=new_policy
        )
        bills.update(conn, edited, today=today, now=NOW)
        assert not conn.in_transaction
        after = {o.id: o for o in _rows(conn, edited)}

        # Overdue, moved-by-hand, and resolved payments are untouched.
        for oid, occ in protected.items():
            assert after[oid] == occ

        new_schedule = set(expand(new_rule, s.dtstart, s.dtstart, date(2040, 1, 1), until=s.until))
        for oid, occ in after.items():
            if oid in protected:
                continue
            # Every other row follows the new schedule, price, and weekend policy...
            assert occ.status is OccurrenceStatus.UPCOMING
            assert occ.nominal_date in new_schedule
            assert replace(occ, id=None, note=None) == new_occurrence(edited, occ.nominal_date)
            # ...and nothing was back-filled into the past.
            if oid not in before:
                assert occ.nominal_date >= today

        # Afterwards, materializing again is a no-op.
        assert payments.materialize(conn, today, now=NOW) == 0


def _strip_ids(rows: list[Occurrence]) -> list[Occurrence]:
    return [replace(o, id=None) for o in rows]
