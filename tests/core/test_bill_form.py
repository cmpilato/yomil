from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from yomil.core.bill_form import (
    BillFormInput,
    Field,
    check_bill,
    form_from_series,
    new_bill_form,
    schedule_summary,
)
from yomil.core.models import AmountKind, WeekendPolicy
from yomil.core.recurrence import monthly_on_day
from yomil.core.schedule import Repeat, Schedule

from ..conftest import make_series

TODAY = date(2026, 3, 10)


def good_form(**overrides: object) -> BillFormInput:
    form = replace(new_bill_form(TODAY), payee="Gas Co", amount_text="45.10")
    return replace(form, **overrides)  # type: ignore[arg-type]


def test_new_bill() -> None:
    check = check_bill(good_form(first_due=date(2026, 3, 31)), base=None)
    assert check.messages == {}
    assert check.series is not None
    assert check.series.id is None
    assert check.series.payee == "Gas Co"
    assert check.series.rrule == monthly_on_day(31)
    assert check.series.dtstart == date(2026, 3, 31)
    assert check.series.expected_amount_cents == 4_510
    assert check.series.active


def test_blank_form_explains_what_is_missing() -> None:
    check = check_bill(new_bill_form(TODAY), base=None)
    assert check.series is None
    assert set(check.messages) == {Field.PAYEE, Field.AMOUNT}
    assert all(m.is_error for m in check.messages.values())


def test_variable_bill_needs_no_amount() -> None:
    check = check_bill(good_form(amount_kind=AmountKind.VARIABLE, amount_text=""), base=None)
    assert check.series is not None
    assert check.series.expected_amount_cents is None


def test_bad_amount() -> None:
    check = check_bill(good_form(amount_text="12.345"), base=None)
    assert check.series is None
    assert check.messages[Field.AMOUNT].is_error


def test_duplicate_name_is_only_a_hint() -> None:
    check = check_bill(good_form(payee=" gas co "), base=None, other_payees=["Gas Co"])
    assert check.series is not None
    assert not check.messages[Field.PAYEE].is_error


def test_until_before_first_due() -> None:
    check = check_bill(good_form(until=date(2026, 3, 1)), base=None)
    assert check.series is None
    assert Field.UNTIL in check.messages


def test_one_time_bill_ignores_until() -> None:
    form = good_form(schedule=Schedule(Repeat.ONCE), until=date(2020, 1, 1))
    check = check_bill(form, base=None)
    assert check.series is not None
    assert check.series.until is None


@pytest.mark.parametrize(
    ("text", "url", "error"),
    [
        ("", None, False),
        ("example.com/pay", "https://example.com/pay", False),
        ("http://example.com", "http://example.com", False),
        ("file:///etc/passwd", None, True),
        ("example.com/my bill", None, True),
    ],
)
def test_url(text: str, url: str | None, error: bool) -> None:
    check = check_bill(good_form(url=text), base=None)
    assert (Field.URL in check.messages) is error
    if not error:
        assert check.series is not None
        assert check.series.url == url


def test_edit_keeps_hidden_fields_and_round_trips() -> None:
    base = make_series(
        id=7,
        lead_days=(5,),
        active=False,
        rrule=monthly_on_day(3, interval=3),
        dtstart=date(2026, 1, 3),
        weekend_policy=WeekendPolicy.PREVIOUS_BUSINESS_DAY,
        url="https://example.com",
        category="Utilities",
        notes="Call first",
    )
    form = form_from_series(base)
    assert form.schedule == Schedule(Repeat.MONTHLY, 3)
    check = check_bill(form, base=base)
    assert check.series == base  # unchanged form, unchanged bill


def test_custom_schedule_keeps_its_rule() -> None:
    base = make_series(id=1, rrule="FREQ=DAILY;INTERVAL=10")
    form = form_from_series(base)
    assert form.schedule.repeat is Repeat.CUSTOM
    check = check_bill(replace(form, payee="Renamed"), base=base)
    assert check.series is not None
    assert check.series.rrule == "FREQ=DAILY;INTERVAL=10"
    with pytest.raises(ValueError, match="custom"):
        check_bill(form, base=None)


def test_summary_for_new_monthly_bill() -> None:
    form = good_form(first_due=date(2026, 11, 15))
    assert schedule_summary(form, base=None, today=TODAY, count=3) == [
        "Every month on the 15th",
        "Next due: Nov 15 · Dec 15 · Jan 15, 2027",
    ]


def test_summary_warns_about_overdue_on_new_bill() -> None:
    form = good_form(first_due=date(2026, 1, 15))
    lines = schedule_summary(form, base=None, today=TODAY, count=1)
    assert lines[1:] == ["Next due: Mar 15", "2 payments before today will be listed as overdue."]


def test_summary_one_time() -> None:
    form = good_form(schedule=Schedule(Repeat.ONCE), first_due=date(2026, 4, 1))
    assert schedule_summary(form, base=None, today=TODAY) == ["One time only", "Due: Apr 1"]


def test_summary_ended_schedule() -> None:
    form = good_form(first_due=date(2025, 1, 15), until=date(2025, 6, 30))
    base = make_series(id=1, dtstart=date(2025, 1, 15), until=date(2025, 6, 30))
    lines = schedule_summary(form, base=base, today=TODAY)
    assert lines == ["Every month on the 15th", "No more due dates: the schedule has ended."]


def test_summary_notes_schedule_change_on_edit() -> None:
    base = make_series(id=1)
    form = form_from_series(base)
    assert len(schedule_summary(form, base=base, today=TODAY)) == 2
    moved = replace(form, first_due=date(2026, 1, 20))
    assert schedule_summary(moved, base=base, today=TODAY)[-1].startswith("Upcoming payments")


def test_clamped_month_end_bill_round_trips() -> None:
    base = make_series(id=1, rrule=monthly_on_day(31), dtstart=date(2026, 4, 30))
    form = form_from_series(base)
    assert form.schedule == Schedule(Repeat.MONTHLY, 1, 31)
    assert check_bill(form, base=base).series == base


def test_reminder_days_come_from_the_form() -> None:
    base = make_series(id=7)
    form = replace(form_from_series(base), lead_days=(14, 0))
    check = check_bill(form, base=base)
    assert check.series is not None
    assert check.series.lead_days == (14, 0)
    assert new_bill_form(TODAY).lead_days == (7, 3, 0)
