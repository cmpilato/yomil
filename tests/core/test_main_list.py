from __future__ import annotations

from datetime import date

from yomil.core.main_list import build_main_list
from yomil.core.models import Occurrence, Series
from yomil.core.urgency import Urgency

TODAY = date(2026, 3, 10)


def _series(sid: int, payee: str) -> Series:
    return Series(id=sid, payee=payee, rrule="FREQ=MONTHLY", dtstart=date(2026, 1, 1))


def _occ(sid: int, due: date) -> Occurrence:
    return Occurrence(
        id=None, series_id=sid, nominal_date=due, due_date=due, expected_amount_cents=100
    )


def test_one_row_per_bill_with_oldest_payment_and_overdue_count() -> None:
    elec, rent = _series(1, "Electric"), _series(2, "rent")
    rows = build_main_list(
        [
            (elec, _occ(1, date(2026, 3, 1))),
            (elec, _occ(1, date(2026, 1, 1))),
            (elec, _occ(1, date(2026, 2, 1))),
            (elec, _occ(1, date(2026, 4, 1))),  # future: not counted as overdue
            (rent, _occ(2, date(2026, 3, 12))),
        ],
        TODAY,
        7,
    )
    assert [(r.series.payee, r.occurrence.due_date, r.more_overdue, r.urgency) for r in rows] == [
        ("Electric", date(2026, 1, 1), 2, Urgency.OVERDUE),
        ("rent", date(2026, 3, 12), 0, Urgency.DUE_SOON),
    ]


def test_sorted_by_due_date_then_name_ignoring_case() -> None:
    due = date(2026, 4, 1)
    rows = build_main_list(
        [
            (_series(1, "water"), _occ(1, due)),
            (_series(2, "Cable"), _occ(2, due)),
            (_series(3, "Zoo"), _occ(3, date(2026, 3, 20))),
        ],
        TODAY,
        7,
    )
    assert [r.series.payee for r in rows] == ["Zoo", "Cable", "water"]
    assert all(r.urgency is Urgency.LATER for r in rows)


def test_empty() -> None:
    assert build_main_list([], TODAY, 7) == []
