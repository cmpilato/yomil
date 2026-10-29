"""Checks for the bill editor's fields, run on every change. Pure.

:func:`check_bill` turns the raw field values into a :class:`Series` ready to save, or
explains (per field) why it can't yet.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from yomil.core.errors import ValidationError
from yomil.core.formatting import USD, format_money_for_entry, parse_money
from yomil.core.forms import FieldMessage
from yomil.core.models import AmountKind, Series, WeekendPolicy
from yomil.core.schedule import Repeat, Schedule, describe, parse_schedule, preview
from yomil.core.validation import validate_series

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import date

    from yomil.core.formatting import MoneyFormat


class Field(enum.StrEnum):
    """Which field a message belongs next to (``FORM``: at the bottom of the dialog)."""

    PAYEE = "payee"
    UNTIL = "until"
    AMOUNT = "amount"
    URL = "url"
    FORM = "form"


@dataclass(frozen=True, slots=True)
class BillFormInput:
    """The editor's field values, as entered."""

    payee: str
    first_due: date
    schedule: Schedule
    until: date | None = None
    weekend_policy: WeekendPolicy = WeekendPolicy.NONE
    amount_kind: AmountKind = AmountKind.FIXED
    amount_text: str = ""
    autopay: bool = False
    category: str = ""
    url: str = ""
    notes: str = ""


@dataclass(frozen=True, slots=True)
class BillCheck:
    series: Series | None  # None while any message is an error
    messages: dict[Field, FieldMessage] = field(default_factory=dict)


def new_bill_form(today: date) -> BillFormInput:
    return BillFormInput(payee="", first_due=today, schedule=Schedule(Repeat.MONTHLY))


def form_from_series(s: Series, fmt: MoneyFormat = USD) -> BillFormInput:
    return BillFormInput(
        payee=s.payee,
        first_due=s.dtstart,
        schedule=parse_schedule(s.rrule, s.dtstart),
        until=s.until,
        weekend_policy=s.weekend_policy,
        amount_kind=s.amount_kind,
        amount_text=(
            ""
            if s.expected_amount_cents is None
            else format_money_for_entry(s.expected_amount_cents, fmt)
        ),
        autopay=s.autopay,
        category=s.category or "",
        url=s.url or "",
        notes=s.notes or "",
    )


def check_bill(
    form: BillFormInput,
    *,
    base: Series | None,
    other_payees: Collection[str] = (),
    fmt: MoneyFormat = USD,
) -> BillCheck:
    """Build the bill ``form`` describes: new if ``base`` is None, else an edit of ``base``.

    ``other_payees`` are the names of her other bills, to point out a likely duplicate.
    """
    messages: dict[Field, FieldMessage] = {}

    payee = form.payee.strip()
    if not payee:
        messages[Field.PAYEE] = FieldMessage("The bill needs a name.", is_error=True)
    elif payee.casefold() in {p.casefold() for p in other_payees}:
        messages[Field.PAYEE] = FieldMessage(
            "You already have a bill with this name.", is_error=False
        )

    cents = None
    try:
        cents = parse_money(form.amount_text, fmt)
    except ValidationError as exc:
        messages[Field.AMOUNT] = FieldMessage(str(exc), is_error=True)
    else:
        if cents is None and form.amount_kind is AmountKind.FIXED:
            messages[Field.AMOUNT] = FieldMessage(
                "Needed for a bill that's the same every time.", is_error=True
            )

    once = form.schedule.repeat is Repeat.ONCE
    until = None if once else form.until
    if until is not None and until < form.first_due:
        messages[Field.UNTIL] = FieldMessage(
            "The end date can't be before the first due date.", is_error=True
        )

    url, url_message = _clean_url(form.url)
    if url_message:
        messages[Field.URL] = url_message

    if form.schedule.repeat is Repeat.CUSTOM:
        if base is None:
            msg = "a new bill can't have a custom schedule"
            raise ValueError(msg)
        rrule = base.rrule
    else:
        rrule = form.schedule.to_rrule(form.first_due)

    if any(m.is_error for m in messages.values()):
        return BillCheck(None, messages)

    # Edits keep what the form doesn't show (id, active, reminder days).
    template = base or Series(id=None, payee="", rrule="", dtstart=form.first_due)
    series = replace(
        template,
        payee=payee,
        rrule=rrule,
        dtstart=form.first_due,
        until=until,
        weekend_policy=form.weekend_policy,
        amount_kind=form.amount_kind,
        expected_amount_cents=cents,
        autopay=form.autopay,
        category=form.category.strip() or None,
        url=url,
        notes=form.notes.strip() or None,
    )
    try:
        validate_series(series)  # the services check again; this catches anything missed
    except ValidationError as exc:
        messages[Field.FORM] = FieldMessage(str(exc), is_error=True)
        return BillCheck(None, messages)
    return BillCheck(series, messages)


def _clean_url(text: str) -> tuple[str | None, FieldMessage | None]:
    """Blank -> None; "example.com" -> "https://example.com"; only web links allowed."""
    url = text.strip()
    if not url:
        return None, None
    if "://" not in url:
        url = f"https://{url}"
    if not url.lower().startswith(("http://", "https://")):
        return None, FieldMessage("Web addresses start with http:// or https://.", is_error=True)
    if " " in url:
        return None, FieldMessage("Web addresses can't contain spaces.", is_error=True)
    return url, None


def schedule_summary(
    form: BillFormInput, *, base: Series | None, today: date, count: int = 5
) -> list[str]:
    """Lines under the schedule fields: what it means, the next due dates, and side effects.

    Works on half-finished forms too (it ignores the name and amount).
    """
    lines = [describe(form.schedule, form.first_due)]
    once = form.schedule.repeat is Repeat.ONCE
    until = None if once or (form.until and form.until < form.first_due) else form.until
    if form.schedule.repeat is Repeat.CUSTOM:
        rrule = base.rrule if base else ""
    else:
        rrule = form.schedule.to_rrule(form.first_due)
    probe = Series(
        id=None,
        payee="",
        rrule=rrule,
        dtstart=form.first_due,
        until=until,
        weekend_policy=form.weekend_policy,
    )
    upcoming = preview(probe, today, count)
    if upcoming.upcoming:
        label = "Due" if once else "Next due"
        lines.append(f"{label}: {' · '.join(_short_date(d, today) for d in upcoming.upcoming)}")
    else:
        lines.append(
            "No more due dates: the schedule has ended." if upcoming.past else "No due dates."
        )
    if base is None and upcoming.past:
        n = upcoming.past
        lines.append(
            f"{n} {'payment' if n == 1 else 'payments'} before today will be listed as overdue."
        )
    if base is not None and (probe.rrule, probe.dtstart, probe.until, probe.weekend_policy) != (
        base.rrule,
        base.dtstart,
        base.until,
        base.weekend_policy,
    ):
        lines.append("Upcoming payments you haven't changed by hand will follow the new schedule.")
    return lines


def _short_date(d: date, today: date) -> str:
    """``"Mar 15"``, with the year only when it isn't this year's."""
    text = f"{d:%b} {d.day}"
    return text if d.year == today.year else f"{text}, {d.year}"
