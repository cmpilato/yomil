from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from yomil.core.main_list import BillRow
from yomil.core.models import AmountKind, Occurrence
from yomil.core.reminders import (
    Reminder,
    due_reminders,
    in_quiet_hours,
    merge_lead_days,
    notices,
    quiet_hours_text,
    reminder_key,
)
from yomil.core.urgency import Urgency

from ..conftest import make_series

TODAY = date(2026, 3, 10)


def _row(
    days: int,
    *,
    sid: int = 1,
    lead_days: tuple[int, ...] = (7, 3, 0),
    kind: AmountKind = AmountKind.FIXED,
    more_overdue: int = 0,
) -> BillRow:
    due = TODAY + timedelta(days=days)
    series = make_series(id=sid, payee=f"Bill {sid}", lead_days=lead_days, amount_kind=kind)
    occ = Occurrence(
        id=sid * 10, series_id=sid, nominal_date=due, due_date=due, expected_amount_cents=10_000
    )
    return BillRow(series, occ, Urgency.LATER, more_overdue)


@pytest.mark.parametrize(
    ("days", "key"),
    [(10, None), (7, 7), (5, 7), (3, 3), (1, 3), (0, 0), (-1, -1), (-6, -6)],
)
def test_reminder_key(days: int, key: int | None) -> None:
    assert reminder_key((7, 3, 0), TODAY + timedelta(days=days), TODAY) == key


def test_no_lead_days_means_no_reminders_even_overdue() -> None:
    assert reminder_key((), TODAY - timedelta(days=3), TODAY) is None


def test_due_reminders_skips_sent_ones() -> None:
    row = _row(2)
    [reminder] = due_reminders([row], TODAY, sent=set())
    assert (reminder.occurrence_id, reminder.key) == (10, 3)
    assert due_reminders([row], TODAY, sent={(10, 3)}) == []
    # A missed day doesn't resend an earlier, less urgent reminder either.
    assert due_reminders([_row(2)], TODAY, sent={(10, 3), (10, 7)}) == []


def test_overdue_reminds_daily() -> None:
    sent = {(10, -1)}
    assert due_reminders([_row(-1)], TODAY, sent) == []
    [again] = due_reminders([_row(-2)], TODAY, sent)
    assert again.key == -2


@pytest.mark.parametrize(
    ("row", "text"),
    [
        (_row(0), "Due today. $100.00."),
        (_row(1), "Due tomorrow (Wed Mar 11, 2026). $100.00."),
        (_row(3, kind=AmountKind.ESTIMATED), "Due in 3 days (Fri Mar 13, 2026). About $100.00."),
        (_row(7, kind=AmountKind.VARIABLE), "Due in 7 days (Tue Mar 17, 2026)."),
        (
            _row(-2, more_overdue=1),
            "Overdue by 2 days (was due Sun Mar 8, 2026). 1 more payment also overdue. $100.00.",
        ),
    ],
)
def test_reminder_text(row: BillRow, text: str) -> None:
    [reminder] = due_reminders([row], TODAY, sent=set())
    assert reminder.text == text


def _reminder(sid: int, key: int) -> Reminder:
    return Reminder(sid, sid * 10, key, f"Bill {sid}", "text")


def test_few_reminders_get_a_notice_each() -> None:
    result = notices([_reminder(1, 3), _reminder(2, 0)])
    assert [(n.title, n.series_id) for n in result] == [("Bill 1", 1), ("Bill 2", 2)]


def test_many_reminders_are_combined() -> None:
    reminders = [_reminder(1, -1), _reminder(2, 3), _reminder(3, 0), _reminder(4, -5)]
    [notice] = notices(reminders)
    assert notice.title == "4 bills need attention"
    assert notice.body == "Bill 1, Bill 2, and 2 more. 2 are overdue."
    assert notice.series_id is None
    assert notice.reminders == tuple(reminders)


@pytest.mark.parametrize(
    ("t", "quiet"),
    [(time(7, 59), True), (time(8, 0), False), (time(20, 59), False), (time(21, 0), True)],
)
def test_quiet_hours(t: time, quiet: bool) -> None:
    assert in_quiet_hours(t) is quiet


def test_merge_lead_days_keeps_days_the_checkboxes_dont_offer() -> None:
    assert merge_lead_days({7, 0}, original=(7, 3, 0)) == (7, 0)
    assert merge_lead_days({14}, original=(5, 3)) == (14, 5)
    assert merge_lead_days(set(), original=()) == ()


def test_quiet_hours_text() -> None:
    assert quiet_hours_text() == "Reminders wait until morning: none between 9 PM and 8 AM."
