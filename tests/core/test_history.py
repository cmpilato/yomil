from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from yomil.core.history import (
    HISTORY_COLUMNS,
    history_cells,
    history_csv_row,
    history_date,
    payment_details,
    unresolve_question,
)
from yomil.core.models import Occurrence, OccurrenceStatus

from ..conftest import make_series

SERIES = make_series(id=1, payee="Electric")
PAID = Occurrence(
    id=7,
    series_id=1,
    nominal_date=date(2026, 3, 15),
    due_date=date(2026, 3, 16),
    expected_amount_cents=10_000,
    status=OccurrenceStatus.PAID,
    payee_snapshot="Electric",
    paid_date=date(2026, 3, 12),
    actual_amount_cents=9_817,
    note="Paid by phone,\nconfirmation 1234",
    reconciled_at=datetime(2026, 3, 12, 15, 0, tzinfo=UTC),
)
SKIPPED = replace(
    PAID, status=OccurrenceStatus.SKIPPED, paid_date=None, actual_amount_cents=None, note=None
)


def test_history_date() -> None:
    assert history_date(PAID) == date(2026, 3, 12)
    assert history_date(SKIPPED) == date(2026, 3, 16)


def test_history_cells_paid() -> None:
    cells = history_cells(PAID, SERIES)
    assert len(cells) == len(HISTORY_COLUMNS)
    assert cells == (
        "Thu Mar 12, 2026",
        "Electric",
        "$98.17",
        "Paid",
        "Paid by phone, confirmation 1234",
    )


def test_history_cells_skipped() -> None:
    assert history_cells(SKIPPED, SERIES) == ("Mon Mar 16, 2026", "Electric", "—", "Skipped", "")


def test_history_uses_the_name_it_had_when_paid() -> None:
    renamed = replace(SERIES, payee="Power Co.")
    assert history_cells(PAID, renamed)[1] == "Electric"
    assert ("Bill now called:", "Power Co.") in payment_details(PAID, renamed)


def test_payment_details_paid() -> None:
    assert payment_details(PAID, SERIES) == [
        ("Status:", "Paid"),
        ("Due date:", "Mon Mar 16, 2026"),
        ("Paid on:", "Thu Mar 12, 2026"),
        ("Amount paid:", "$98.17"),
        ("Expected amount:", "$100.00"),
        ("Note:", "Paid by phone,\nconfirmation 1234"),
    ]


def test_payment_details_omits_expected_amount_when_it_matches() -> None:
    exact = replace(PAID, actual_amount_cents=10_000)
    assert "Expected amount:" not in dict(payment_details(exact, SERIES))


def test_payment_details_skipped() -> None:
    assert payment_details(SKIPPED, SERIES) == [
        ("Status:", "Skipped"),
        ("Due date:", "Mon Mar 16, 2026"),
        ("Note:", "—"),
    ]


def test_unresolve_question() -> None:
    assert unresolve_question(PAID, SERIES).startswith(
        "Mark the Electric payment due Mon Mar 16, 2026 as not paid?"
    )
    assert unresolve_question(SKIPPED, SERIES).startswith("Undo skipping")
    assert "retired" not in unresolve_question(PAID, SERIES)
    assert "is retired" in unresolve_question(PAID, replace(SERIES, active=False))


def test_history_csv_row() -> None:
    assert history_csv_row(PAID, SERIES) == (
        "2026-03-12",
        "Electric",
        "Paid",
        "98.17",
        "2026-03-16",
        "Paid by phone,\nconfirmation 1234",
    )
    assert history_csv_row(replace(PAID, actual_amount_cents=5), SERIES)[3] == "0.05"
    assert history_csv_row(SKIPPED, SERIES) == (
        "2026-03-16",
        "Electric",
        "Skipped",
        "",
        "2026-03-16",
        "",
    )
