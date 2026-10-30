"""How pressing a due date is, relative to today."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

DEFAULT_THRESHOLD_DAYS = 7


class Urgency(enum.StrEnum):
    OVERDUE = "overdue"
    DUE_SOON = "due_soon"
    LATER = "later"


def classify(due_date: date, today: date, threshold_days: int) -> Urgency:
    """``OVERDUE`` before today; ``DUE_SOON`` from today through ``threshold_days`` ahead."""
    if threshold_days < 0:
        msg = f"threshold_days must be >= 0, got {threshold_days}"
        raise ValueError(msg)
    days_left = (due_date - today).days
    if days_left < 0:
        return Urgency.OVERDUE
    if days_left <= threshold_days:
        return Urgency.DUE_SOON
    return Urgency.LATER
