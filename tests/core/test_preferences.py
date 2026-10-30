from __future__ import annotations

from datetime import date

import pytest

from yomil.core.preferences import sample_rows, threshold_explanation
from yomil.core.urgency import Urgency

TODAY = date(2026, 3, 10)


@pytest.mark.parametrize(
    ("threshold", "urgencies"),
    [
        (0, [Urgency.OVERDUE, Urgency.LATER, Urgency.LATER]),
        (7, [Urgency.OVERDUE, Urgency.DUE_SOON, Urgency.LATER]),
        (14, [Urgency.OVERDUE, Urgency.DUE_SOON, Urgency.DUE_SOON]),
    ],
)
def test_sample_rows_follow_the_threshold(threshold: int, urgencies: list[Urgency]) -> None:
    rows = sample_rows(TODAY, threshold)
    assert [r.urgency for r in rows] == urgencies
    assert rows[0].occurrence.due_date < TODAY


@pytest.mark.parametrize(
    ("days", "text"),
    [
        (0, "Only bills due today are shown as due soon."),
        (1, "Bills due today or tomorrow are shown as due soon."),
        (7, "Bills due in the next 7 days are shown as due soon."),
    ],
)
def test_threshold_explanation(days: int, text: str) -> None:
    assert threshold_explanation(days) == text
