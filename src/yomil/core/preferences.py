"""What the Preferences dialog shows while the user tries settings out. Pure."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from yomil.core.main_list import build_main_list
from yomil.core.models import AmountKind, Occurrence, Series

if TYPE_CHECKING:
    from datetime import date

    from yomil.core.main_list import BillRow

# (bill, days from today, expected cents, kind): one overdue, one due in a few days, and
# one further out, so changing the "due soon" window visibly recolors the sample.
_SAMPLE_BILLS = (
    ("Water & Sewer", -2, 6_500, AmountKind.FIXED),
    ("Electric Company", 3, 12_000, AmountKind.ESTIMATED),
    ("Rent", 10, 125_000, AmountKind.FIXED),
)


def sample_rows(today: date, threshold_days: int) -> list[BillRow]:
    """Made-up main-list rows for the live preview."""
    pairs = []
    for i, (payee, days, cents, kind) in enumerate(_SAMPLE_BILLS, start=1):
        due = today + timedelta(days=days)
        series = Series(
            id=i,
            payee=payee,
            rrule="FREQ=MONTHLY",
            dtstart=due,
            amount_kind=kind,
            expected_amount_cents=cents,
        )
        occ = Occurrence(
            id=i, series_id=i, nominal_date=due, due_date=due, expected_amount_cents=cents
        )
        pairs.append((series, occ))
    return build_main_list(pairs, today, threshold_days)


def threshold_explanation(days: int) -> str:
    if days == 0:
        return "Only bills due today are shown as due soon."
    if days == 1:
        return "Bills due today or tomorrow are shown as due soon."
    return f"Bills due in the next {days} days are shown as due soon."
