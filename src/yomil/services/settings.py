"""Typed access to app preferences stored in the ``setting`` table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from yomil.core.errors import ValidationError
from yomil.core.urgency import DEFAULT_THRESHOLD_DAYS
from yomil.storage import settings as settings_repo

if TYPE_CHECKING:
    import sqlite3

UPCOMING_THRESHOLD_DAYS = "upcoming_threshold_days"


def upcoming_threshold_days(conn: sqlite3.Connection) -> int:
    """How many days ahead a payment counts as "due soon"."""
    raw = settings_repo.get(conn, UPCOMING_THRESHOLD_DAYS)
    try:
        return DEFAULT_THRESHOLD_DAYS if raw is None else max(0, int(raw))
    except ValueError:
        return DEFAULT_THRESHOLD_DAYS


def set_upcoming_threshold_days(conn: sqlite3.Connection, days: int) -> None:
    if not 0 <= days <= 365:
        raise ValidationError("The 'due soon' window must be between 0 and 365 days.")
    settings_repo.put(conn, UPCOMING_THRESHOLD_DAYS, str(days))
