from __future__ import annotations

from datetime import date, timedelta

import pytest

from yomil.core.urgency import Urgency, classify

TODAY = date(2026, 3, 10)


@pytest.mark.parametrize(
    ("offset", "threshold", "expected"),
    [
        (-30, 7, Urgency.OVERDUE),
        (-1, 7, Urgency.OVERDUE),
        (0, 7, Urgency.DUE_SOON),
        (7, 7, Urgency.DUE_SOON),
        (8, 7, Urgency.LATER),
        (0, 0, Urgency.DUE_SOON),
        (1, 0, Urgency.LATER),
    ],
)
def test_classify(offset: int, threshold: int, expected: Urgency) -> None:
    assert classify(TODAY + timedelta(days=offset), TODAY, threshold) is expected


def test_classify_rejects_negative_threshold() -> None:
    with pytest.raises(ValueError, match="threshold_days"):
        classify(TODAY, TODAY, -1)
