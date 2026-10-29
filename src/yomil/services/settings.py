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


LIST_FONT_SIZE = "list_font_size"


def list_font_size(conn: sqlite3.Connection) -> int | None:
    """Point size for the lists, or ``None`` for the system default."""
    raw = settings_repo.get(conn, LIST_FONT_SIZE)
    try:
        return None if raw is None else _check_font_size(int(raw))
    except (ValueError, ValidationError):
        return None


def set_list_font_size(conn: sqlite3.Connection, points: int | None) -> None:
    if points is None:
        settings_repo.delete(conn, LIST_FONT_SIZE)
    else:
        settings_repo.put(conn, LIST_FONT_SIZE, str(_check_font_size(points)))


def _check_font_size(points: int) -> int:
    if not 6 <= points <= 72:
        raise ValidationError("The font size must be between 6 and 72 points.")
    return points
