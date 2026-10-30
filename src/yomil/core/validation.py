"""Input checks shared by the services. Each raises :class:`ValidationError` with a
message phrased for the user."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dateutil.rrule import rrulestr

from yomil.core.errors import ValidationError
from yomil.core.models import AmountKind

if TYPE_CHECKING:
    from yomil.core.models import Series


def validate_amount(cents: int | None, *, required: bool, what: str = "Amount") -> None:
    if cents is None:
        if required:
            raise ValidationError(f"{what} is required.")
        return
    if cents < 0:
        raise ValidationError(f"{what} can't be negative.")


def validate_series(s: Series) -> None:
    if not s.payee.strip():
        raise ValidationError("The bill needs a name.")
    validate_amount(
        s.expected_amount_cents,
        required=s.amount_kind is AmountKind.FIXED,
        what="Expected amount",
    )
    if s.until is not None and s.until < s.dtstart:
        raise ValidationError("The end date can't be before the first due date.")
    if any(d < 0 for d in s.lead_days):
        raise ValidationError("Reminder days can't be negative.")
    try:
        rrulestr(s.rrule)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"The schedule isn't valid ({exc}).") from exc
