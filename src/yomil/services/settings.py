"""Typed access to app preferences stored in the ``setting`` table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from yomil.core.errors import ValidationError
from yomil.core.urgency import DEFAULT_THRESHOLD_DAYS
from yomil.storage import settings as settings_repo
from yomil.storage.db import transaction

if TYPE_CHECKING:
    import sqlite3

UPCOMING_THRESHOLD_DAYS = "upcoming_threshold_days"
MIN_THRESHOLD_DAYS = 0
MAX_THRESHOLD_DAYS = 365


def upcoming_threshold_days(conn: sqlite3.Connection) -> int:
    """How many days ahead a payment counts as "due soon"."""
    raw = settings_repo.get(conn, UPCOMING_THRESHOLD_DAYS)
    try:
        return DEFAULT_THRESHOLD_DAYS if raw is None else max(0, int(raw))
    except ValueError:
        return DEFAULT_THRESHOLD_DAYS


def set_upcoming_threshold_days(conn: sqlite3.Connection, days: int) -> None:
    settings_repo.put(conn, UPCOMING_THRESHOLD_DAYS, str(_check_threshold(days)))


def _check_threshold(days: int) -> int:
    if not MIN_THRESHOLD_DAYS <= days <= MAX_THRESHOLD_DAYS:
        msg = (
            "The 'due soon' window must be between "
            f"{MIN_THRESHOLD_DAYS} and {MAX_THRESHOLD_DAYS} days."
        )
        raise ValidationError(msg)
    return days


FONT_SIZE = "font_size"
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 36


def font_size(conn: sqlite3.Connection) -> int | None:
    """Point size for all of YOMIL's windows, or ``None`` for the Windows default."""
    raw = settings_repo.get(conn, FONT_SIZE)
    try:
        return None if raw is None else _check_font_size(int(raw))
    except (ValueError, ValidationError):
        return None


def set_font_size(conn: sqlite3.Connection, points: int | None) -> None:
    if points is None:
        settings_repo.delete(conn, FONT_SIZE)
    else:
        settings_repo.put(conn, FONT_SIZE, str(_check_font_size(points)))


def save_preferences(
    conn: sqlite3.Connection, *, font_size: int | None, upcoming_threshold_days: int
) -> None:
    """Save the Preferences dialog: all or nothing."""
    if font_size is not None:
        _check_font_size(font_size)
    _check_threshold(upcoming_threshold_days)
    with transaction(conn):
        set_font_size(conn, font_size)
        set_upcoming_threshold_days(conn, upcoming_threshold_days)


def _check_font_size(points: int) -> int:
    if not MIN_FONT_SIZE <= points <= MAX_FONT_SIZE:
        msg = f"The text size must be between {MIN_FONT_SIZE} and {MAX_FONT_SIZE} points."
        raise ValidationError(msg)
    return points
