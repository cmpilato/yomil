from __future__ import annotations

from datetime import date, timedelta

import pytest

from yomil.core.errors import ValidationError
from yomil.core.formatting import (
    USD,
    MoneyFormat,
    format_date,
    format_expected_amount,
    format_money,
    format_money_for_entry,
    money_format_from_localeconv,
    parse_money,
    quick_pay_amount,
    status_text,
    summary_text,
)
from yomil.core.main_list import BillRow
from yomil.core.models import AmountKind, Occurrence
from yomil.core.urgency import classify

from ..conftest import make_series

TODAY = date(2026, 3, 10)


def make_row(
    offset: int = 0,
    *,
    expected: int | None = 10_000,
    kind: AmountKind = AmountKind.FIXED,
    more_overdue: int = 0,
) -> BillRow:
    due = TODAY + timedelta(days=offset)
    series = make_series(id=1, amount_kind=kind, expected_amount_cents=expected)
    occ = Occurrence(
        id=1, series_id=1, nominal_date=due, due_date=due, expected_amount_cents=expected
    )
    return BillRow(series, occ, classify(due, TODAY, 7), more_overdue)


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (0, "$0.00"),
        (5, "$0.05"),
        (8_917, "$89.17"),
        (125_000, "$1,250.00"),
        (123_456_789, "$1,234,567.89"),
        (-1_050, "-$10.50"),
    ],
)
def test_format_money_usd(cents: int, expected: str) -> None:
    assert format_money(cents) == expected


def test_format_money_symbol_after_with_space() -> None:
    euro = MoneyFormat(
        symbol="€", symbol_first=False, space=True, decimal_point=",", thousands_sep="."
    )
    assert format_money(123_456, euro) == "1.234,56 €"


def test_money_format_from_localeconv() -> None:
    conv = {
        "currency_symbol": "£",
        "p_cs_precedes": 1,
        "p_sep_by_space": 0,
        "mon_decimal_point": ".",
        "mon_thousands_sep": ",",
    }
    assert format_money(123_456, money_format_from_localeconv(conv)) == "£1,234.56"


def test_money_format_falls_back_to_usd_for_c_locale() -> None:
    # What locale.localeconv() returns under the "C" locale.
    conv = {"currency_symbol": "", "p_cs_precedes": 127, "mon_decimal_point": ""}
    assert money_format_from_localeconv(conv) == USD


def test_format_date() -> None:
    assert format_date(date(2026, 3, 3)) == "Tue Mar 3, 2026"


@pytest.mark.parametrize(
    ("kind", "expected", "text"),
    [
        (AmountKind.FIXED, 8_917, "$89.17"),
        (AmountKind.ESTIMATED, 12_000, "About $120.00"),
        (AmountKind.VARIABLE, 12_000, "About $120.00"),
        (AmountKind.VARIABLE, None, "Varies"),
    ],
)
def test_format_expected_amount(kind: AmountKind, expected: int | None, text: str) -> None:
    assert format_expected_amount(make_row(expected=expected, kind=kind)) == text


@pytest.mark.parametrize(
    ("offset", "more", "text"),
    [
        (-1, 0, "⚠ OVERDUE by 1 day"),
        (-3, 0, "⚠ OVERDUE by 3 days"),
        (-40, 1, "⚠ OVERDUE by 40 days (+1 more overdue)"),
        (0, 0, "Due today"),
        (1, 0, "Due tomorrow"),
        (7, 0, "Due in 7 days"),
        (12, 0, "In 12 days"),
    ],
)
def test_status_text(offset: int, more: int, text: str) -> None:
    assert status_text(make_row(offset, more_overdue=more), TODAY) == text


def test_quick_pay_amount() -> None:
    assert quick_pay_amount(make_row(expected=8_917)) == 8_917
    assert quick_pay_amount(make_row(expected=None, kind=AmountKind.VARIABLE)) is None


@pytest.mark.parametrize(
    ("offsets", "text"),
    [
        ([], "Nothing overdue or due soon."),
        ([30], "Nothing overdue or due soon."),
        ([-1], "1 bill overdue"),
        ([-1, -5, 2, 30], "2 bills overdue, 1 due soon"),
        ([2], "1 bill due soon"),
        ([0, 2], "2 bills due soon"),
    ],
)
def test_summary_text(offsets: list[int], text: str) -> None:
    assert summary_text([make_row(o) for o in offsets]) == text


EURO = MoneyFormat(symbol="€", symbol_first=False, space=True, decimal_point=",", thousands_sep=".")


@pytest.mark.parametrize(("cents", "text"), [(0, "0.00"), (5, "0.05"), (123_456, "1234.56")])
def test_format_money_for_entry(cents: int, text: str) -> None:
    assert format_money_for_entry(cents) == text
    assert parse_money(text) == cents


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("", None),
        ("   ", None),
        ("$", None),
        ("12", 1_200),
        ("12.", 1_200),
        ("12.5", 1_250),
        (".5", 50),
        (" $1,234.56 ", 123_456),
        ("$ 89.17", 8_917),
    ],
)
def test_parse_money(text: str, cents: int | None) -> None:
    assert parse_money(text) == cents


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("-5", "negative"),
        ("12.345", "two digits"),
        ("abc", "like \\$123.45"),
        ("1.2.3", "like"),
        (".", "like"),
        ("١٢", "like"),  # non-ASCII digits
        ("999999999", "too large"),
    ],
)
def test_parse_money_rejects(text: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_money(text)


def test_parse_money_in_another_locale() -> None:
    assert parse_money("1.234,5 €", EURO) == 123_450
    assert format_money_for_entry(123_450, EURO) == "1234,50"
