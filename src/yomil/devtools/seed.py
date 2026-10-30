"""Fill a scratch database with realistic bills, relative to today.

Usage: ``python -m yomil.devtools.seed PATH [--today YYYY-MM-DD]`` (or ``make seed``).
Refuses to touch an existing file.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from yomil.core.models import AmountKind, Series, WeekendPolicy
from yomil.core.recurrence import monthly_on_day
from yomil.services import bills, payments
from yomil.storage import db

if TYPE_CHECKING:
    import sqlite3


def _months_ago(today: date, months: int, day: int) -> date:
    """``day`` of the month ``months`` before ``today``'s, clamped to that month's end."""
    total = today.year * 12 + today.month - 1 - months
    year, month = divmod(total, 12)
    first_of_next = date(year + (month + 1) // 12, (month + 1) % 12 + 1, 1)
    return date(year, month + 1, min(day, (first_of_next - timedelta(days=1)).day))


def seed(conn: sqlite3.Connection, today: date) -> None:
    """Create bills with history, a couple of overdue payments, and edge cases."""
    bill_defs = [
        Series(
            id=None,
            payee="Electric Company",
            rrule=monthly_on_day(15),
            dtstart=_months_ago(today, 6, 15),
            amount_kind=AmountKind.VARIABLE,
            category="Utilities",
            url="https://example.com/electric",
        ),
        Series(
            id=None,
            payee="Rent",
            rrule=monthly_on_day(1),
            dtstart=_months_ago(today, 6, 1),
            expected_amount_cents=125_000,
            notes="Check to the landlord, or drop off at the office.",
        ),
        Series(  # month-end clamping
            id=None,
            payee="Car Insurance",
            rrule=monthly_on_day(31),
            dtstart=_months_ago(today, 6, 31),
            expected_amount_cents=8_917,
            autopay=True,
        ),
        Series(  # quarterly, with weekend adjustment
            id=None,
            payee="Water & Sewer",
            rrule=monthly_on_day(3, interval=3),
            dtstart=_months_ago(today, 9, 3),
            amount_kind=AmountKind.ESTIMATED,
            expected_amount_cents=6_500,
            weekend_policy=WeekendPolicy.PREVIOUS_BUSINESS_DAY,
        ),
        Series(
            id=None,
            payee="Newspaper",
            rrule="FREQ=WEEKLY;INTERVAL=4",
            dtstart=today - timedelta(weeks=20),
            expected_amount_cents=2_400,
        ),
        Series(  # one-time, coming up soon
            id=None,
            payee="Property Tax (2nd half)",
            rrule="FREQ=YEARLY;COUNT=1",
            dtstart=today + timedelta(days=3),
            expected_amount_cents=184_233,
            category="Taxes",
        ),
        Series(
            id=None,
            payee="Old Cable TV",
            rrule=monthly_on_day(20),
            dtstart=_months_ago(today, 2, 20),
            expected_amount_cents=9_999,
        ),
    ]
    created = {s.payee: bills.create(conn, s, today=today) for s in bill_defs}

    # Work down history, leaving recent payments pending so some are overdue.
    for payee, keep_pending in (
        ("Electric Company", 2),  # two overdue: shows "(+1 more overdue)"
        ("Rent", 1),
        ("Car Insurance", 1),
        ("Water & Sewer", 1),
        ("Newspaper", 1),
        ("Old Cable TV", 0),
    ):
        _resolve_all_but(conn, created[payee], keep_pending, today)

    retired_id = created["Old Cable TV"].id
    assert retired_id is not None
    bills.retire(conn, retired_id)


def _resolve_all_but(conn: sqlite3.Connection, series: Series, keep: int, today: date) -> None:
    """Pay (or occasionally skip) past-due payments, oldest first, until ``keep`` remain."""
    assert series.id is not None
    overdue = [
        o for o in payments.for_bill(conn, series.id) if not o.resolved and o.due_date < today
    ]
    for occ in overdue[: max(0, len(overdue) - keep)]:
        assert occ.id is not None
        if occ.nominal_date.month % 5 == 0:
            payments.skip(conn, occ.id, note="Waived this month", today=today)
            continue
        amount = occ.expected_amount_cents
        if amount is None:  # variable bill: make up a plausible amount
            amount = 11_000 + 137 * occ.nominal_date.month
        payments.reconcile(
            conn,
            occ.id,
            paid_date=occ.due_date - timedelta(days=2),
            actual_amount_cents=amount,
            note=None,
            today=today,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m yomil.devtools.seed")
    parser.add_argument("path", type=Path)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())  # noqa: DTZ011
    args = parser.parse_args(argv)
    if args.path.exists():
        parser.error(f"{args.path} already exists; delete it first")
    args.path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(args.path)
    db.migrate(conn)
    seed(conn, args.today)
    conn.close()
    sys.stderr.write(f"Seeded {args.path} as of {args.today}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
