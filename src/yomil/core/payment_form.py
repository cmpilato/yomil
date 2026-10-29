"""Checks for the Event Editor's fields, run on every keystroke. Pure.

The dialog shows each :class:`FieldMessage` next to its field instead of popping up error
boxes, and enables Mark Paid only when :attr:`PaymentCheck.can_mark_paid`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from yomil.core.errors import ValidationError
from yomil.core.formatting import USD, parse_money

if TYPE_CHECKING:
    from datetime import date

    from yomil.core.formatting import MoneyFormat


@dataclass(frozen=True, slots=True)
class FieldMessage:
    text: str
    is_error: bool  # an error blocks Mark Paid; otherwise it's just a hint


@dataclass(frozen=True, slots=True)
class PaymentCheck:
    amount_cents: int | None
    amount_message: FieldMessage | None = None
    paid_date_message: FieldMessage | None = None

    @property
    def can_mark_paid(self) -> bool:
        return self.amount_cents is not None


def check_payment(
    amount_text: str, paid_date: date, today: date, fmt: MoneyFormat = USD
) -> PaymentCheck:
    """Parse the amount and comment on anything she might want to look at again."""
    paid_msg = None
    if paid_date > today:
        paid_msg = FieldMessage("That date is in the future. Is that right?", is_error=False)
    try:
        cents = parse_money(amount_text, fmt)
    except ValidationError as exc:
        return PaymentCheck(None, FieldMessage(str(exc), is_error=True), paid_msg)
    if cents is None:
        return PaymentCheck(None, FieldMessage("Needed to mark it paid.", is_error=False), paid_msg)
    return PaymentCheck(cents, None, paid_msg)
