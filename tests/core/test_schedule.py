from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from yomil.core.models import WeekendPolicy
from yomil.core.recurrence import expand, monthly_on_day
from yomil.core.schedule import (
    Repeat,
    Schedule,
    SchedulePreview,
    describe,
    parse_schedule,
    preview,
)

from ..conftest import make_series

TODAY = date(2026, 3, 10)

schedules = st.one_of(
    st.just(Schedule(Repeat.ONCE)),
    st.builds(
        Schedule,
        st.sampled_from([Repeat.WEEKLY, Repeat.MONTHLY, Repeat.YEARLY]),
        st.integers(1, 12),
    ),
)


@given(schedules, st.dates(date(2000, 1, 1), date(2040, 12, 31)))
def test_round_trip_and_first_due_is_first_occurrence(schedule: Schedule, first: date) -> None:
    rule = schedule.to_rrule(first)
    assert parse_schedule(rule, first) == schedule
    [found] = expand(rule, first, first, first)
    assert found == first


@pytest.mark.parametrize(
    ("rule", "first", "expected"),
    [
        ("FREQ=YEARLY;COUNT=1", date(2026, 3, 20), Schedule(Repeat.ONCE)),
        ("FREQ=WEEKLY;INTERVAL=4", date(2026, 3, 3), Schedule(Repeat.WEEKLY, 4)),
        (monthly_on_day(15), date(2026, 1, 15), Schedule(Repeat.MONTHLY)),
        (monthly_on_day(31), date(2026, 1, 31), Schedule(Repeat.MONTHLY)),
        (monthly_on_day(3, interval=3), date(2026, 1, 3), Schedule(Repeat.MONTHLY, 3)),
        # "The 31st", first due on a clamped month-end.
        (monthly_on_day(31), date(2026, 4, 30), Schedule(Repeat.MONTHLY, 1, 31)),
        (monthly_on_day(30, interval=2), date(2026, 2, 28), Schedule(Repeat.MONTHLY, 2, 30)),
        # The day in the rule doesn't match the first due date: not one of ours.
        (monthly_on_day(31), date(2026, 4, 29), Schedule(Repeat.CUSTOM)),
        (monthly_on_day(15), date(2026, 1, 20), Schedule(Repeat.CUSTOM)),
        ("FREQ=MONTHLY", date(2026, 1, 1), Schedule(Repeat.CUSTOM)),
        ("FREQ=DAILY;INTERVAL=2", date(2026, 1, 1), Schedule(Repeat.CUSTOM)),
    ],
)
def test_parse_schedule(rule: str, first: date, expected: Schedule) -> None:
    assert parse_schedule(rule, first) == expected


def test_feb_29_yearly_falls_back_to_feb_28() -> None:
    first = date(2028, 2, 29)
    rule = Schedule(Repeat.YEARLY).to_rrule(first)
    assert expand(rule, first, first, date(2030, 12, 31)) == [
        date(2028, 2, 29),
        date(2029, 2, 28),
        date(2030, 2, 28),
    ]


def test_custom_has_no_rule() -> None:
    with pytest.raises(ValueError, match="custom"):
        Schedule(Repeat.CUSTOM).to_rrule(TODAY)


@pytest.mark.parametrize(
    ("schedule", "first", "text"),
    [
        (Schedule(Repeat.ONCE), date(2026, 3, 3), "One time only"),
        (Schedule(Repeat.WEEKLY), date(2026, 3, 3), "Every week on Tuesday"),
        (Schedule(Repeat.WEEKLY, 2), date(2026, 3, 3), "Every 2 weeks on Tuesday"),
        (Schedule(Repeat.MONTHLY), date(2026, 3, 1), "Every month on the 1st"),
        (Schedule(Repeat.MONTHLY, 3), date(2026, 3, 3), "Every 3 months on the 3rd"),
        (Schedule(Repeat.MONTHLY), date(2026, 3, 12), "Every month on the 12th"),
        (Schedule(Repeat.MONTHLY), date(2026, 3, 22), "Every month on the 22nd"),
        (
            Schedule(Repeat.MONTHLY),
            date(2026, 3, 31),
            "Every month on the 31st (or the last day of shorter months)",
        ),
        (
            Schedule(Repeat.MONTHLY, 1, 31),
            date(2026, 4, 30),
            "Every month on the 31st (or the last day of shorter months)",
        ),
        (Schedule(Repeat.YEARLY), date(2026, 3, 3), "Every year on March 3"),
        (Schedule(Repeat.YEARLY, 2), date(2026, 3, 3), "Every 2 years on March 3"),
        (
            Schedule(Repeat.YEARLY),
            date(2028, 2, 29),
            "Every year on February 29 (February 28 in other years)",
        ),
        (Schedule(Repeat.CUSTOM), date(2026, 3, 3), "Custom schedule"),
    ],
)
def test_describe(schedule: Schedule, first: date, text: str) -> None:
    assert describe(schedule, first) == text


def test_preview_future_bill() -> None:
    s = make_series(dtstart=date(2026, 4, 15))
    p = preview(s, TODAY, count=3)
    assert p.upcoming == [date(2026, 4, 15), date(2026, 5, 15), date(2026, 6, 15)]
    assert p.past == 0


def test_preview_counts_past_due_dates() -> None:
    s = make_series(dtstart=date(2026, 1, 15))  # Jan and Feb are before TODAY
    p = preview(s, TODAY, count=2)
    assert p.upcoming == [date(2026, 3, 15), date(2026, 4, 15)]
    assert p.past == 2


def test_preview_applies_weekend_policy_and_until() -> None:
    s = make_series(
        dtstart=date(2026, 3, 15),  # a Sunday
        until=date(2026, 4, 30),
        weekend_policy=WeekendPolicy.NEXT_BUSINESS_DAY,
    )
    assert preview(s, TODAY).upcoming == [date(2026, 3, 16), date(2026, 4, 15)]


def test_preview_one_time_in_the_past() -> None:
    s = make_series(rrule="FREQ=YEARLY;COUNT=1", dtstart=date(2026, 1, 2))
    assert preview(s, TODAY) == SchedulePreview([], 1)
