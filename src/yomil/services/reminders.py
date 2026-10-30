"""Reminder notifications: which are due now, and remembering which were shown.

Showing a reminder isn't a change to a bill or payment, so it's not in ``event_log``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from yomil.core.formatting import USD
from yomil.core.reminders import due_reminders
from yomil.services import payments
from yomil.services._audit import utc_now
from yomil.storage import reminders as reminders_repo
from yomil.storage.db import transaction

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterable
    from datetime import date, datetime

    from yomil.core.formatting import MoneyFormat
    from yomil.core.reminders import Reminder


def due(conn: sqlite3.Connection, today: date, fmt: MoneyFormat = USD) -> list[Reminder]:
    """Reminders that should be shown now and haven't been. Read-only."""
    return due_reminders(payments.main_list(conn, today), today, reminders_repo.sent(conn), fmt)


def mark_shown(
    conn: sqlite3.Connection, reminders: Iterable[Reminder], *, now: datetime | None = None
) -> None:
    with transaction(conn):
        reminders_repo.mark_sent(
            conn, ((r.occurrence_id, r.key) for r in reminders), now or utc_now()
        )
