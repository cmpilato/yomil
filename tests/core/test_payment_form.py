from __future__ import annotations

from datetime import date, timedelta

from yomil.core.payment_form import FieldMessage, PaymentCheck, check_payment

TODAY = date(2026, 3, 10)


def test_valid_amount() -> None:
    check = check_payment("89.17", TODAY, TODAY)
    assert check == PaymentCheck(8_917)
    assert check.can_mark_paid


def test_blank_amount_is_a_hint_not_an_error() -> None:
    check = check_payment("  ", TODAY, TODAY)
    assert not check.can_mark_paid
    assert check.amount_message == FieldMessage("Needed to mark it paid.", is_error=False)


def test_bad_amount_is_an_error() -> None:
    check = check_payment("12.345", TODAY, TODAY)
    assert not check.can_mark_paid
    assert check.amount_message is not None
    assert check.amount_message.is_error


def test_future_paid_date_is_allowed_with_a_hint() -> None:
    check = check_payment("1", TODAY + timedelta(days=1), TODAY)
    assert check.can_mark_paid
    assert check.paid_date_message is not None
    assert not check.paid_date_message.is_error
    assert check_payment("1", TODAY, TODAY).paid_date_message is None


def test_both_messages_at_once() -> None:
    check = check_payment("x", TODAY + timedelta(days=3), TODAY)
    assert check.amount_message is not None
    assert check.paid_date_message is not None
