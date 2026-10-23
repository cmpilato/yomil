from __future__ import annotations

import calendar
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from yomil.core.models import WeekendPolicy
from yomil.core.recurrence import apply_weekend_policy, expand, monthly_on_day


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def test_monthly_simple_day() -> None:
    got = expand(monthly_on_day(15), date(2026, 1, 15), date(2026, 1, 1), date(2026, 4, 30))
    assert got == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15), date(2026, 4, 15)]


def test_monthly_31st_clamps_to_month_end() -> None:
    got = expand(monthly_on_day(31), date(2026, 1, 31), date(2026, 1, 1), date(2026, 5, 31))
    assert got == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
    ]


def test_monthly_30th_in_leap_february() -> None:
    got = expand(monthly_on_day(30), date(2028, 1, 30), date(2028, 2, 1), date(2028, 2, 29))
    assert got == [date(2028, 2, 29)]


def test_quarterly_interval() -> None:
    got = expand(
        monthly_on_day(1, interval=3), date(2026, 1, 1), date(2026, 1, 1), date(2026, 12, 31)
    )
    assert got == [date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1)]


def test_until_truncates_window() -> None:
    got = expand(
        monthly_on_day(10),
        date(2026, 1, 10),
        date(2026, 1, 1),
        date(2026, 12, 31),
        until=date(2026, 3, 10),
    )
    assert got == [date(2026, 1, 10), date(2026, 2, 10), date(2026, 3, 10)]


def test_empty_when_window_is_before_until_or_inverted() -> None:
    assert expand(monthly_on_day(1), date(2026, 1, 1), date(2026, 5, 1), date(2026, 4, 1)) == []
    assert (
        expand(
            monthly_on_day(1),
            date(2026, 1, 1),
            date(2026, 6, 1),
            date(2026, 7, 1),
            until=date(2026, 3, 1),
        )
        == []
    )


@pytest.mark.parametrize("bad_day", [0, 32, -1])
def test_monthly_on_day_rejects_bad_day(bad_day: int) -> None:
    with pytest.raises(ValueError, match="day must be"):
        monthly_on_day(bad_day)


@given(day=st.integers(1, 31), start_year=st.integers(2000, 2100))
def test_monthly_always_hits_clamped_day_every_month(day: int, start_year: int) -> None:
    got = expand(
        monthly_on_day(day),
        date(start_year, 1, 1),
        date(start_year, 1, 1),
        date(start_year + 2, 12, 31),
    )
    assert len(got) == 36  # exactly one per month, none skipped
    for d in got:
        assert d.day == min(day, _last_day(d.year, d.month))


# 2026-03-14 is a Saturday; 2026-03-15 Sunday; 2026-03-13 Friday; 2026-03-16 Monday.
@pytest.mark.parametrize(
    ("nominal", "policy", "expected"),
    [
        (date(2026, 3, 14), WeekendPolicy.NONE, date(2026, 3, 14)),
        (date(2026, 3, 14), WeekendPolicy.PREVIOUS_BUSINESS_DAY, date(2026, 3, 13)),
        (date(2026, 3, 15), WeekendPolicy.PREVIOUS_BUSINESS_DAY, date(2026, 3, 13)),
        (date(2026, 3, 14), WeekendPolicy.NEXT_BUSINESS_DAY, date(2026, 3, 16)),
        (date(2026, 3, 15), WeekendPolicy.NEXT_BUSINESS_DAY, date(2026, 3, 16)),
        (date(2026, 3, 13), WeekendPolicy.NEXT_BUSINESS_DAY, date(2026, 3, 13)),
    ],
)
def test_weekend_policy(nominal: date, policy: WeekendPolicy, expected: date) -> None:
    assert apply_weekend_policy(nominal, policy) == expected


@given(d=st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31)))
def test_weekend_policy_always_lands_on_a_weekday(d: date) -> None:
    for policy in (WeekendPolicy.PREVIOUS_BUSINESS_DAY, WeekendPolicy.NEXT_BUSINESS_DAY):
        assert apply_weekend_policy(d, policy).weekday() < 5
