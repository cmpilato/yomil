"""Bill editor: add a bill, or change one.

The schedule is "how often" plus a first due date; the day it falls on comes from that
date (see ``core.schedule``). All rules live in ``core.bill_form``. Messages appear next
to a field once she has touched it, or for every field after she tries to save.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
import wx.adv

from yomil.app.dates import from_wx, to_wx
from yomil.app.fields import grow_to_fit, show_message
from yomil.core.bill_form import (
    BillFormInput,
    Field,
    check_bill,
    form_from_series,
    new_bill_form,
    schedule_summary,
)
from yomil.core.errors import YomilError
from yomil.core.models import AmountKind, WeekendPolicy
from yomil.core.schedule import Repeat, Schedule
from yomil.services import bills

if TYPE_CHECKING:
    import sqlite3
    from datetime import date

    from yomil.core.bill_form import BillCheck
    from yomil.core.formatting import MoneyFormat
    from yomil.core.models import Series

_REPEATS = [
    (Repeat.ONCE, "One time only", ""),
    (Repeat.WEEKLY, "Weekly", "week"),
    (Repeat.MONTHLY, "Monthly", "month"),
    (Repeat.YEARLY, "Yearly", "year"),
]
_CUSTOM = (Repeat.CUSTOM, "Custom (set up outside YOMIL)", "")
_WEEKEND_POLICIES = [
    (WeekendPolicy.NONE, "Keep the date"),
    (WeekendPolicy.PREVIOUS_BUSINESS_DAY, "Move it to the Friday before"),
    (WeekendPolicy.NEXT_BUSINESS_DAY, "Move it to the Monday after"),
]
_AMOUNT_KINDS = [
    (AmountKind.FIXED, "The same every time"),
    (AmountKind.ESTIMATED, "About the same each time"),
    (AmountKind.VARIABLE, "Different every time"),
]


class BillEditor(wx.Dialog):
    """Modal. After ``ShowModal() == wx.ID_OK``, :attr:`saved` is the stored bill."""

    def __init__(
        self,
        parent: wx.Window,
        conn: sqlite3.Connection,
        base: Series | None,
        *,
        money_fmt: MoneyFormat,
        today: date,
    ) -> None:
        title = "Add a Bill" if base is None else f"Edit Bill: {base.payee}"
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.saved: Series | None = None
        self._conn = conn
        self._base = base
        self._money_fmt = money_fmt
        self._today = today
        others = [s for s in bills.list_all(conn) if base is None or s.id != base.id]
        self._other_payees = [s.payee for s in others]
        categories = sorted({s.category for s in bills.list_all(conn) if s.category})
        self._touched: set[Field] = set()
        self._show_all = False

        form = new_bill_form(today) if base is None else form_from_series(base, money_fmt)
        # A clamped "31st" survives only while the first due date it was read from does.
        self._month_day = (form.schedule.month_day, form.first_due)
        self._repeats = [*_REPEATS, _CUSTOM] if form.schedule.repeat is Repeat.CUSTOM else _REPEATS

        gap = self.FromDIP(8)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._build_basics(form, categories), 0, wx.EXPAND | wx.ALL, 2 * gap)
        sizer.Add(self._build_schedule(form), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 2 * gap)
        sizer.Add(self._build_amount(form), 0, wx.EXPAND | wx.ALL, 2 * gap)
        sizer.Add(self._build_other(form), 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 2 * gap)
        self._form_msg = wx.StaticText(self)
        sizer.Add(self._form_msg, 0, wx.LEFT | wx.RIGHT | wx.TOP, 2 * gap)
        sizer.Add(self._build_buttons(), 0, wx.EXPAND | wx.ALL, 2 * gap)
        self.SetSizerAndFit(sizer)

        self._initial = self._form()
        self._update()
        self.SetMinSize(self.GetSize())
        self.CentreOnParent()
        self._payee.SetFocus()

    # ------------------------------------------------------------------ layout

    def _grid(self) -> wx.FlexGridSizer:
        grid = wx.FlexGridSizer(cols=2, vgap=self.FromDIP(4), hgap=self.FromDIP(12))
        grid.AddGrowableCol(1)
        return grid

    def _row(
        self, grid: wx.FlexGridSizer, parent: wx.Window, label: str, control: wx.Window | wx.Sizer
    ) -> None:
        grid.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(control, 0, wx.EXPAND)

    def _message_row(self, grid: wx.FlexGridSizer, parent: wx.Window) -> wx.StaticText:
        msg = wx.StaticText(parent)
        grid.AddSpacer(0)
        grid.Add(msg)
        return msg

    def _section(self, title: str) -> tuple[wx.StaticBoxSizer, wx.StaticBox]:
        """A titled box. Controls inside it must be children of its StaticBox (wx 3.x)."""
        box = wx.StaticBoxSizer(wx.VERTICAL, self, title)
        return box, box.GetStaticBox()

    def _finish_section(self, box: wx.StaticBoxSizer, grid: wx.FlexGridSizer) -> wx.Sizer:
        box.Add(grid, 1, wx.EXPAND | wx.ALL, self.FromDIP(8))
        return box

    def _build_basics(self, form: BillFormInput, categories: list[str]) -> wx.Sizer:
        grid = self._grid()
        self._payee = wx.TextCtrl(self, value=form.payee, size=self.FromDIP(wx.Size(320, -1)))
        self._row(grid, self, "&Name:", self._payee)
        self._payee_msg = self._message_row(grid, self)
        self._category = wx.ComboBox(self, value=form.category, choices=categories)
        self._row(grid, self, "Ca&tegory (optional):", self._category)
        self._payee.Bind(wx.EVT_TEXT, lambda _evt: self._touch(Field.PAYEE))
        return grid

    def _build_schedule(self, form: BillFormInput) -> wx.Sizer:
        box, p = self._section("When it's due")
        grid = self._grid()
        style = wx.adv.DP_DROPDOWN | wx.adv.DP_SHOWCENTURY
        self._first_due = wx.adv.DatePickerCtrl(p, dt=to_wx(form.first_due), style=style)
        self._row(grid, p, "&First due date:", self._first_due)

        self._repeat = wx.Choice(p, choices=[label for _r, label, _u in self._repeats])
        self._repeat.SetSelection([r for r, _l, _u in self._repeats].index(form.schedule.repeat))
        self._every_label = wx.StaticText(p, label="every")
        self._interval = wx.SpinCtrl(p, min=1, max=99, initial=form.schedule.interval)
        self._unit_label = wx.StaticText(p)
        repeat_row = wx.BoxSizer(wx.HORIZONTAL)
        repeat_row.Add(self._repeat, 0, wx.ALIGN_CENTER_VERTICAL)
        for item in (self._every_label, self._interval, self._unit_label):
            repeat_row.Add(item, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.FromDIP(8))
        self._row(grid, p, "&Repeats:", repeat_row)

        self._has_until = wx.CheckBox(p, label="&Ends on")
        self._has_until.SetValue(form.until is not None)
        self._until = wx.adv.DatePickerCtrl(p, dt=to_wx(form.until or form.first_due), style=style)
        until_row = wx.BoxSizer(wx.HORIZONTAL)
        until_row.Add(self._has_until, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.FromDIP(8))
        until_row.Add(self._until)
        grid.AddSpacer(0)
        grid.Add(until_row)
        self._until_msg = self._message_row(grid, p)

        self._weekend = wx.Choice(p, choices=[label for _p, label in _WEEKEND_POLICIES])
        self._weekend.SetSelection(
            [pol for pol, _l in _WEEKEND_POLICIES].index(form.weekend_policy)
        )
        self._row(grid, p, "If due on a &weekend:", self._weekend)

        self._summary = wx.StaticText(p)
        grid.AddSpacer(0)
        grid.Add(self._summary, 0, wx.TOP, self.FromDIP(4))

        self._first_due.Bind(wx.adv.EVT_DATE_CHANGED, lambda _evt: self._touch(Field.UNTIL))
        self._repeat.Bind(wx.EVT_CHOICE, lambda _evt: self._update())
        self._interval.Bind(wx.EVT_SPINCTRL, lambda _evt: self._update())
        self._interval.Bind(wx.EVT_TEXT, lambda _evt: self._update())
        self._has_until.Bind(wx.EVT_CHECKBOX, lambda _evt: self._touch(Field.UNTIL))
        self._until.Bind(wx.adv.EVT_DATE_CHANGED, lambda _evt: self._touch(Field.UNTIL))
        self._weekend.Bind(wx.EVT_CHOICE, lambda _evt: self._update())
        return self._finish_section(box, grid)

    def _build_amount(self, form: BillFormInput) -> wx.Sizer:
        box, p = self._section("Amount")
        grid = self._grid()
        self._amount_kind = wx.Choice(p, choices=[label for _k, label in _AMOUNT_KINDS])
        self._amount_kind.SetSelection([k for k, _l in _AMOUNT_KINDS].index(form.amount_kind))
        self._row(grid, p, "The a&mount is:", self._amount_kind)
        self._amount = wx.TextCtrl(p, value=form.amount_text)
        self._amount_label = wx.StaticText(p, label="E&xpected amount:")
        grid.Add(self._amount_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._amount, 0, wx.EXPAND)
        self._amount_msg = self._message_row(grid, p)
        self._autopay = wx.CheckBox(p, label="Paid &automatically (autopay)")
        self._autopay.SetValue(form.autopay)
        grid.AddSpacer(0)
        grid.Add(self._autopay)

        self._amount_kind.Bind(wx.EVT_CHOICE, lambda _evt: self._touch(Field.AMOUNT))
        self._amount.Bind(wx.EVT_TEXT, lambda _evt: self._touch(Field.AMOUNT))
        return self._finish_section(box, grid)

    def _build_other(self, form: BillFormInput) -> wx.Sizer:
        box, p = self._section("Other details")
        grid = self._grid()
        grid.AddGrowableRow(2)  # notes
        self._url = wx.TextCtrl(p, value=form.url)
        self._row(grid, p, "Web site for &paying:", self._url)
        self._url_msg = self._message_row(grid, p)
        self._notes = wx.TextCtrl(
            p, value=form.notes, style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(-1, 60))
        )
        grid.Add(wx.StaticText(p, label="N&otes:"), 0, wx.TOP, self.FromDIP(4))
        grid.Add(self._notes, 1, wx.EXPAND)
        self._url.Bind(wx.EVT_TEXT, lambda _evt: self._touch(Field.URL))
        return self._finish_section(box, grid)

    def _build_buttons(self) -> wx.Sizer:
        save = wx.Button(self, wx.ID_SAVE, label="&Save")
        cancel = wx.Button(self, wx.ID_CANCEL, label="&Cancel")  # also Escape and the X
        save.SetDefault()
        save.Bind(wx.EVT_BUTTON, self._on_save)
        cancel.Bind(wx.EVT_BUTTON, self._on_cancel)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.AddStretchSpacer()
        sizer.Add(save, 0, wx.RIGHT, self.FromDIP(8))
        sizer.Add(cancel)
        return sizer

    # ------------------------------------------------------------ field state

    def _form(self) -> BillFormInput:
        repeat = self._repeats[self._repeat.GetSelection()][0]
        first_due = from_wx(self._first_due.GetValue())
        month_day, month_day_first_due = self._month_day
        if repeat is not Repeat.MONTHLY or first_due != month_day_first_due:
            month_day = None
        interval = 1 if repeat is Repeat.ONCE else self._interval.GetValue()
        return BillFormInput(
            payee=self._payee.GetValue(),
            first_due=first_due,
            schedule=Schedule(repeat, interval, month_day),
            until=from_wx(self._until.GetValue()) if self._has_until.GetValue() else None,
            weekend_policy=_WEEKEND_POLICIES[self._weekend.GetSelection()][0],
            amount_kind=_AMOUNT_KINDS[self._amount_kind.GetSelection()][0],
            amount_text=self._amount.GetValue(),
            autopay=self._autopay.GetValue(),
            category=self._category.GetValue(),
            url=self._url.GetValue(),
            notes=self._notes.GetValue(),
        )

    def _check(self) -> BillCheck:
        return check_bill(
            self._form(), base=self._base, other_payees=self._other_payees, fmt=self._money_fmt
        )

    def _touch(self, field: Field) -> None:
        self._touched.add(field)
        self._update()

    def _update(self) -> None:
        form = self._form()
        check = self._check()
        for field, label in (
            (Field.PAYEE, self._payee_msg),
            (Field.UNTIL, self._until_msg),
            (Field.AMOUNT, self._amount_msg),
            (Field.URL, self._url_msg),
            (Field.FORM, self._form_msg),
        ):
            shown = self._show_all or field in self._touched
            show_message(label, check.messages.get(field) if shown else None)

        repeat, _label, unit = self._repeats[self._repeat.GetSelection()]
        repeating = repeat not in (Repeat.ONCE, Repeat.CUSTOM)
        n = self._interval.GetValue()
        self._unit_label.SetLabel(unit if n == 1 else f"{unit}s")
        for item in (self._every_label, self._interval, self._unit_label):
            item.Show(repeating)
        recurring = repeat is not Repeat.ONCE
        for until_item in (self._has_until, self._until):
            until_item.Show(recurring)
        self._until.Enable(self._has_until.GetValue())
        self._amount_label.SetLabel(
            "E&xpected amount:"
            if form.amount_kind is AmountKind.FIXED
            else "E&xpected amount (optional):"
        )

        self._summary.SetLabel(
            "\n".join(schedule_summary(form, base=self._base, today=self._today))
        )
        grow_to_fit(self)

    # ---------------------------------------------------------------- actions

    def _on_save(self, _event: wx.CommandEvent) -> None:
        if self._save():
            self.EndModal(wx.ID_OK)

    def _save(self) -> bool:
        self._show_all = True
        self._update()
        check = self._check()
        if check.series is None:
            self._focus_first_error(check)
            return False
        try:
            if self._base is None:
                self.saved = bills.create(self._conn, check.series, today=self._today)
            else:
                self.saved = bills.update(self._conn, check.series, today=self._today)
        except YomilError as exc:
            wx.MessageBox(str(exc), "YOMIL", wx.OK | wx.ICON_WARNING, self)
            return False
        return True

    def _focus_first_error(self, check: BillCheck) -> None:
        controls = {
            Field.PAYEE: self._payee,
            Field.UNTIL: self._until,
            Field.AMOUNT: self._amount,
            Field.URL: self._url,
        }
        for field, control in controls.items():
            message = check.messages.get(field)
            if message is not None and message.is_error:
                control.SetFocus()
                return

    def _on_cancel(self, _event: wx.CommandEvent) -> None:
        if self._form() != self._initial:
            dlg = wx.MessageDialog(
                self,
                "Save your changes to this bill?",
                "Unsaved Changes",
                wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
            )
            dlg.SetYesNoCancelLabels("&Save", "&Don't Save", "&Keep Editing")
            answer = dlg.ShowModal()
            dlg.Destroy()
            if answer == wx.ID_CANCEL:
                return
            if answer == wx.ID_YES:
                if self._save():
                    self.EndModal(wx.ID_OK)
                return
        self.EndModal(wx.ID_CANCEL)
