from __future__ import annotations

from dataclasses import replace
from datetime import date

from yomil.core.models import Occurrence, OccurrenceStatus, Series, WeekendPolicy
from yomil.core.planning import is_regenerable, plan_materialization, plan_regeneration
from yomil.core.recurrence import monthly_on_day, next_after

from ..conftest import make_series


def _saved(**overrides: object) -> Series:
    return replace(make_series(**overrides), id=1)


def _nominals(occs: list[Occurrence]) -> list[date]:
    return [o.nominal_date for o in occs]


def _paid(o: Occurrence) -> Occurrence:
    return replace(o, status=OccurrenceStatus.PAID)


def test_next_after() -> None:
    rule = monthly_on_day(15)
    assert next_after(rule, date(2026, 1, 15), date(2026, 1, 15)) == date(2026, 2, 15)
    assert next_after(rule, date(2026, 1, 15), date(2026, 1, 14)) == date(2026, 1, 15)
    assert next_after(rule, date(2026, 1, 15), date(2026, 1, 15), until=date(2026, 2, 1)) is None
    assert next_after("FREQ=YEARLY;COUNT=1", date(2026, 1, 15), date(2026, 1, 15)) is None


def test_materialize_backfills_through_today_plus_next() -> None:
    plan = plan_materialization(_saved(), [], date(2026, 3, 20))
    assert _nominals(plan) == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15),
                               date(2026, 4, 15)]  # fmt: skip
    assert all(o.status is OccurrenceStatus.UPCOMING and o.series_id == 1 for o in plan)


def test_new_bill_starting_in_future_gets_only_its_first_payment() -> None:
    plan = plan_materialization(_saved(dtstart=date(2026, 5, 15)), [], date(2026, 3, 1))
    assert _nominals(plan) == [date(2026, 5, 15)]


def test_materialize_only_returns_missing() -> None:
    s = _saved()
    today = date(2026, 3, 20)
    first = plan_materialization(s, [], today)
    assert plan_materialization(s, first, today) == []


def test_paying_ahead_brings_up_the_following_payment() -> None:
    s = _saved()
    today = date(2026, 3, 20)
    existing = plan_materialization(s, [], today)
    existing[-1] = _paid(existing[-1])  # 2026-04-15 paid early
    assert _nominals(plan_materialization(s, existing, today)) == [date(2026, 5, 15)]


def test_inactive_or_ended_series_gets_nothing_new() -> None:
    assert plan_materialization(_saved(active=False), [], date(2026, 3, 20)) == []
    ended = _saved(until=date(2026, 2, 15))
    assert _nominals(plan_materialization(ended, [], date(2026, 6, 1))) == [
        date(2026, 1, 15),
        date(2026, 2, 15),
    ]


def test_weekend_policy_and_amount_applied() -> None:
    # 2026-03-15 is a Sunday.
    s = _saved(weekend_policy=WeekendPolicy.NEXT_BUSINESS_DAY, expected_amount_cents=4_200)
    plan = plan_materialization(s, [], date(2026, 3, 1))
    march = next(o for o in plan if o.nominal_date == date(2026, 3, 15))
    assert march.due_date == date(2026, 3, 16)
    assert march.expected_amount_cents == 4_200


def test_is_regenerable() -> None:
    today = date(2026, 3, 1)
    occ = plan_materialization(_saved(), [], today)[-1]  # 2026-03-15, pending
    assert is_regenerable(occ, today)
    assert is_regenerable(replace(occ, due_date=today), today)
    assert not is_regenerable(replace(occ, due_date=date(2026, 2, 28)), today)  # overdue
    assert not is_regenerable(replace(occ, due_date_overridden=True), today)
    assert not is_regenerable(_paid(occ), today)


def test_regeneration_updates_moves_and_deletes_only_regenerable_rows() -> None:
    today = date(2026, 3, 1)
    old = _saved()
    existing = [
        replace(o, id=i) for i, o in enumerate(plan_materialization(old, [], date(2026, 7, 1)))
    ]
    # Jan 15 overdue, Feb 15 overdue, Mar..Jul future. Override May, pay June ahead.
    by_month = {o.nominal_date.month: o for o in existing}
    by_month[5] = replace(by_month[5], due_date=date(2026, 5, 20), due_date_overridden=True)
    by_month[6] = _paid(by_month[6])
    existing = list(by_month.values())

    # New schedule: every other month from March; new amount.
    new = replace(
        old, rrule=monthly_on_day(15, interval=2), dtstart=date(2026, 3, 15),
        expected_amount_cents=12_345,
    )  # fmt: skip
    plan = plan_regeneration(new, existing, today)
    # Regenerable: Mar, Apr, Jul. The new schedule keeps Mar and Jul (re-priced), drops Apr.
    assert [o.nominal_date.month for o in plan.delete] == [4]
    assert [(o.nominal_date.month, o.expected_amount_cents) for o in plan.update] == [
        (3, 12_345),
        (7, 12_345),
    ]


def test_regeneration_noop_when_nothing_changes() -> None:
    s = _saved()
    existing = [
        replace(o, id=i) for i, o in enumerate(plan_materialization(s, [], date(2026, 6, 1)))
    ]
    plan = plan_regeneration(s, existing, date(2026, 3, 1))
    assert plan.delete == []
    assert plan.update == []
