"""User-facing text for dates, money, and payment status. Pure.

Money formatting takes a :class:`MoneyFormat` rather than reading the process locale, so
it stays deterministic in tests; the app builds one once at startup with
:func:`money_format_from_localeconv`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yomil.core.models import AmountKind
from yomil.core.urgency import Urgency

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from datetime import date

    from yomil.core.main_list import BillRow

OVERDUE_MARK = "⚠"


@dataclass(frozen=True, slots=True)
class MoneyFormat:
    symbol: str = "$"
    symbol_first: bool = True
    space: bool = False  # between the symbol and the number
    decimal_point: str = "."
    thousands_sep: str = ","


USD = MoneyFormat()


def money_format_from_localeconv(conv: Mapping[str, Any]) -> MoneyFormat:
    """Build a format from :func:`locale.localeconv` output; USD if it has no currency."""
    symbol = conv.get("currency_symbol") or ""
    if not symbol:
        return USD
    return MoneyFormat(
        symbol=symbol,
        symbol_first=bool(conv.get("p_cs_precedes", 1)),
        space=conv.get("p_sep_by_space") == 1,
        decimal_point=conv.get("mon_decimal_point") or ".",
        thousands_sep=conv.get("mon_thousands_sep") or "",
    )


def format_money(cents: int, fmt: MoneyFormat = USD) -> str:
    """``123456`` -> ``"$1,234.56"`` (always two decimal places)."""
    units, frac = divmod(abs(cents), 100)
    number = f"{units:,}".replace(",", fmt.thousands_sep) + f"{fmt.decimal_point}{frac:02d}"
    sep = " " if fmt.space else ""
    text = f"{fmt.symbol}{sep}{number}" if fmt.symbol_first else f"{number}{sep}{fmt.symbol}"
    return f"-{text}" if cents < 0 else text


def format_date(d: date) -> str:
    """``"Tue Mar 3, 2026"``: unambiguous, unlike all-numeric dates."""
    return f"{d:%a %b} {d.day}, {d.year}"


def format_expected_amount(row: BillRow, fmt: MoneyFormat = USD) -> str:
    """The Amount column: exact, approximate (estimated bills), or "Varies"."""
    cents = row.occurrence.expected_amount_cents
    if cents is None:
        return "Varies"
    if row.series.amount_kind is AmountKind.FIXED:
        return format_money(cents, fmt)
    return f"About {format_money(cents, fmt)}"


def _days(n: int) -> str:
    return "1 day" if n == 1 else f"{n} days"


def status_text(row: BillRow, today: date) -> str:
    """The Status column, readable without color: "⚠ OVERDUE by 3 days", "Due tomorrow"."""
    days_left = (row.occurrence.due_date - today).days
    if row.urgency is Urgency.OVERDUE:
        text = f"{OVERDUE_MARK} OVERDUE by {_days(-days_left)}"
        if row.more_overdue:
            text += f" (+{row.more_overdue} more overdue)"
        return text
    if days_left == 0:
        return "Due today"
    if days_left == 1:
        return "Due tomorrow"
    if row.urgency is Urgency.DUE_SOON:
        return f"Due in {_days(days_left)}"
    return f"In {_days(days_left)}"


def quick_pay_amount(row: BillRow) -> int | None:
    """What a one-click Mark Paid would record, or ``None`` if the bill has no amount yet."""
    return row.occurrence.expected_amount_cents


def summary_text(rows: Iterable[BillRow]) -> str:
    """One line for the status bar: ``"2 bills overdue, 1 due soon"``."""
    counts = Counter(r.urgency for r in rows)
    overdue, soon = counts[Urgency.OVERDUE], counts[Urgency.DUE_SOON]
    if not overdue and not soon:
        return "Nothing overdue or due soon."
    parts = []
    if overdue:
        parts.append(f"{overdue} {'bill' if overdue == 1 else 'bills'} overdue")
    if soon:
        noun = "" if overdue else (" bill" if soon == 1 else " bills")
        parts.append(f"{soon}{noun} due soon")
    return ", ".join(parts)
