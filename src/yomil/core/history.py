"""What Payment History and the Event Viewer show for a paid or skipped payment. Pure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from yomil.core.formatting import USD, format_date, format_money
from yomil.core.models import OccurrenceStatus

if TYPE_CHECKING:
    from datetime import date

    from yomil.core.formatting import MoneyFormat
    from yomil.core.models import Occurrence, Series

HISTORY_COLUMNS = ("Date", "Bill", "Amount", "Status", "Note")


def history_date(occ: Occurrence) -> date:
    """The date it's listed under: when it was paid, or (if skipped) when it was due."""
    return occ.paid_date or occ.due_date


def bill_name(occ: Occurrence, series: Series) -> str:
    """The bill's name when it was paid or skipped (bills can be renamed since)."""
    return occ.payee_snapshot or series.payee


def history_cells(occ: Occurrence, series: Series, fmt: MoneyFormat = USD) -> tuple[str, ...]:
    """One row of Payment History, matching :data:`HISTORY_COLUMNS`."""
    paid = occ.status is OccurrenceStatus.PAID
    amount = occ.actual_amount_cents
    return (
        format_date(history_date(occ)),
        bill_name(occ, series),
        format_money(amount, fmt) if paid and amount is not None else "—",
        "Paid" if paid else "Skipped",
        " ".join((occ.note or "").split()),  # one line in the list; the viewer shows it all
    )


def payment_details(
    occ: Occurrence, series: Series, fmt: MoneyFormat = USD
) -> list[tuple[str, str]]:
    """``(label, value)`` lines for the Event Viewer."""
    lines: list[tuple[str, str]] = []
    name = bill_name(occ, series)
    if series.payee != name:
        lines.append(("Bill now called:", series.payee))
    if occ.status is OccurrenceStatus.PAID:
        lines.append(("Status:", "Paid"))
        lines.append(("Due date:", format_date(occ.due_date)))
        if occ.paid_date is not None:
            lines.append(("Paid on:", format_date(occ.paid_date)))
        if occ.actual_amount_cents is not None:
            lines.append(("Amount paid:", format_money(occ.actual_amount_cents, fmt)))
        expected = occ.expected_amount_cents
        if expected is not None and expected != occ.actual_amount_cents:
            lines.append(("Expected amount:", format_money(expected, fmt)))
    else:
        lines.append(("Status:", "Skipped"))
        lines.append(("Due date:", format_date(occ.due_date)))
    lines.append(("Note:", occ.note or "—"))
    return lines


def unresolve_question(occ: Occurrence, series: Series) -> str:
    """The confirmation for Mark Unpaid / Undo Skip."""
    name = bill_name(occ, series)
    due = format_date(occ.due_date)
    if occ.status is OccurrenceStatus.PAID:
        text = (
            f"Mark the {name} payment due {due} as not paid?\n\n"
            "Its paid date and amount will be cleared, and it will go back on the "
            "main list as a bill to pay."
        )
    else:
        text = (
            f"Undo skipping the {name} payment due {due}?\n\n"
            "It will go back on the main list as a bill to pay."
        )
    if not series.active:
        text += (
            f"\n\n{series.payee} is retired, so the payment won't appear on the main list "
            "unless you reactivate the bill in Manage Bills."
        )
    return text


CSV_COLUMNS = ("Date", "Bill", "Status", "Amount", "Due date", "Note")


def history_csv_row(occ: Occurrence, series: Series) -> tuple[str, ...]:
    """One row of the exported history, matching :data:`CSV_COLUMNS`.

    Plain values a spreadsheet understands (``2026-03-12``, ``1234.56``), rather than
    the on-screen formatting.
    """
    paid = occ.status is OccurrenceStatus.PAID
    cents = occ.actual_amount_cents
    return (
        history_date(occ).isoformat(),
        bill_name(occ, series),
        "Paid" if paid else "Skipped",
        f"{cents // 100}.{cents % 100:02d}" if paid and cents is not None else "",
        occ.due_date.isoformat(),
        occ.note or "",
    )
