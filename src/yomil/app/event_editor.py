"""Event Editor: work on one pending payment (save, mark paid, or skip).

All field rules live in ``core.payment_form``; this dialog shows its messages next to the
fields while the user types, so nothing pops up an error box for a typo.
"""

from __future__ import annotations

import enum
import logging
from typing import TYPE_CHECKING

import wx
import wx.adv

from yomil.app.dates import from_wx, to_wx
from yomil.app.fields import grow_to_fit, show_message
from yomil.app.fonts import inherit_font
from yomil.core.errors import ValidationError, YomilError
from yomil.core.formatting import (
    format_date,
    format_expected_amount,
    format_money_for_entry,
)
from yomil.core.payment_form import check_payment
from yomil.core.recurrence import apply_weekend_policy
from yomil.services import payments

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable
    from datetime import date

    from yomil.core.formatting import MoneyFormat
    from yomil.core.main_list import BillRow

log = logging.getLogger(__name__)


class Outcome(enum.Enum):
    SAVED = "saved"
    PAID = "paid"
    SKIPPED = "skipped"


class EventEditor(wx.Dialog):
    """Modal. After ``ShowModal()``, :attr:`outcome` says what (if anything) was changed."""

    def __init__(
        self,
        parent: wx.Window,
        conn: sqlite3.Connection,
        row: BillRow,
        *,
        money_fmt: MoneyFormat,
        today: date,
    ) -> None:
        super().__init__(
            parent,
            title=f"Payment: {row.series.payee}",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        inherit_font(self, parent)  # before creating any controls
        assert row.occurrence.id is not None
        self.outcome: Outcome | None = None
        self._conn = conn
        self._row = row
        self._occ_id = row.occurrence.id
        self._money_fmt = money_fmt
        self._today = today

        gap = self.FromDIP(8)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._build_header(), 0, wx.EXPAND | wx.ALL, 2 * gap)
        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 2 * gap)
        sizer.Add(self._build_form(), 1, wx.EXPAND | wx.ALL, 2 * gap)
        sizer.Add(self._build_buttons(), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 2 * gap)
        self.SetSizerAndFit(sizer)
        self.SetMinSize(self.GetSize())
        self.CentreOnParent()

        self._initial = self._current_values()
        self._update_checks()
        self._amount.SetFocus()
        self._amount.SelectAll()

    # ------------------------------------------------------------------ layout

    def _build_header(self) -> wx.Sizer:
        series, occ = self._row.series, self._row.occurrence
        title = wx.StaticText(self, label=series.payee)
        title.SetFont(self.GetFont().Bold().Scaled(1.4))

        grid = wx.FlexGridSizer(cols=2, vgap=self.FromDIP(4), hgap=self.FromDIP(12))
        scheduled = apply_weekend_policy(occ.nominal_date, series.weekend_policy)
        self._add_info(grid, "Scheduled for:", format_date(scheduled))
        self._add_info(grid, "Expected amount:", format_expected_amount(self._row, self._money_fmt))
        if self._row.more_overdue:
            n = self._row.more_overdue
            self._add_info(
                grid,
                "Also overdue:",
                f"{n} more {'payment' if n == 1 else 'payments'} after this one",
            )
        if series.notes:
            notes = self._add_info(grid, "Bill notes:", series.notes)
            notes.Wrap(self.FromDIP(420))
        if series.url:
            grid.Add(wx.StaticText(self, label="Pay online:"), 0, wx.ALIGN_CENTER_VERTICAL)
            if series.url.lower().startswith(("http://", "https://")):
                link_style = wx.adv.HL_ALIGN_LEFT | wx.adv.HL_CONTEXTMENU | wx.NO_BORDER
                grid.Add(
                    wx.adv.HyperlinkCtrl(self, label=series.url, url=series.url, style=link_style)
                )
            else:
                grid.Add(wx.StaticText(self, label=series.url))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title, 0, wx.BOTTOM, self.FromDIP(8))
        sizer.Add(grid)
        return sizer

    def _add_info(self, grid: wx.FlexGridSizer, label: str, value: str) -> wx.StaticText:
        text = wx.StaticText(self, label=value)
        grid.Add(wx.StaticText(self, label=label))
        grid.Add(text)
        return text

    def _build_form(self) -> wx.Sizer:
        occ = self._row.occurrence
        picker_style = wx.adv.DP_DROPDOWN | wx.adv.DP_SHOWCENTURY

        self._due = wx.adv.DatePickerCtrl(self, dt=to_wx(occ.due_date), style=picker_style)
        self._paid = wx.adv.DatePickerCtrl(self, dt=to_wx(self._today), style=picker_style)
        self._paid_msg = wx.StaticText(self)
        expected = occ.expected_amount_cents
        self._amount = wx.TextCtrl(
            self,
            value="" if expected is None else format_money_for_entry(expected, self._money_fmt),
        )
        self._amount_msg = wx.StaticText(self)
        self._note = wx.TextCtrl(
            self, value=occ.note or "", style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(-1, 70))
        )

        self._paid.Bind(wx.adv.EVT_DATE_CHANGED, lambda _evt: self._update_checks())
        self._amount.Bind(wx.EVT_TEXT, lambda _evt: self._update_checks())

        grid = wx.FlexGridSizer(cols=2, vgap=self.FromDIP(4), hgap=self.FromDIP(12))
        grid.AddGrowableCol(1)
        grid.AddGrowableRow(5)  # the note grows with the dialog
        label_flags = wx.ALIGN_CENTER_VERTICAL

        grid.Add(wx.StaticText(self, label="D&ue date:"), 0, label_flags)
        grid.Add(self._due)
        grid.Add(wx.StaticText(self, label="Paid &on:"), 0, label_flags)
        grid.Add(self._paid)
        grid.AddSpacer(0)
        grid.Add(self._paid_msg, 0, wx.BOTTOM, self.FromDIP(4))
        grid.Add(wx.StaticText(self, label="&Amount paid:"), 0, label_flags)
        grid.Add(self._amount, 0, wx.EXPAND)
        grid.AddSpacer(0)
        grid.Add(self._amount_msg, 0, wx.BOTTOM, self.FromDIP(4))
        grid.Add(wx.StaticText(self, label="&Note:"), 0, wx.TOP, self.FromDIP(4))
        grid.Add(self._note, 1, wx.EXPAND)
        return grid

    def _build_buttons(self) -> wx.Sizer:
        self._pay_button = wx.Button(self, label="&Mark Paid")
        save = wx.Button(self, wx.ID_SAVE, label="&Save")
        skip = wx.Button(self, label="S&kip…")
        close = wx.Button(self, wx.ID_CANCEL, label="&Close")  # also Escape and the X
        self._pay_button.SetDefault()  # Enter in the amount field pays

        self._pay_button.Bind(wx.EVT_BUTTON, self._on_mark_paid)
        save.Bind(wx.EVT_BUTTON, self._on_save)
        skip.Bind(wx.EVT_BUTTON, self._on_skip)
        close.Bind(wx.EVT_BUTTON, self._on_close)

        gap = self.FromDIP(8)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        for button in (self._pay_button, save, skip):
            sizer.Add(button, 0, wx.RIGHT, gap)
        sizer.AddStretchSpacer()
        sizer.Add(close)
        return sizer

    # ------------------------------------------------------------ field state

    def _current_values(self) -> tuple[date, str, date, str]:
        return (
            from_wx(self._due.GetValue()),
            self._note.GetValue().strip(),
            from_wx(self._paid.GetValue()),
            self._amount.GetValue().strip(),
        )

    def _update_checks(self) -> None:
        check = check_payment(
            self._amount.GetValue(), from_wx(self._paid.GetValue()), self._today, self._money_fmt
        )
        show_message(self._amount_msg, check.amount_message)
        show_message(self._paid_msg, check.paid_date_message)
        self._pay_button.Enable(check.can_mark_paid)
        grow_to_fit(self)

    # ---------------------------------------------------------------- actions

    def _on_save(self, _event: wx.CommandEvent) -> None:
        if self._save():
            self.EndModal(wx.ID_OK)

    def _save(self) -> bool:
        due, note, _paid, _amount = self._current_values()
        return self._run(
            Outcome.SAVED,
            lambda: payments.update_pending(self._conn, self._occ_id, due_date=due, note=note),
        )

    def _on_mark_paid(self, _event: wx.CommandEvent) -> None:
        due, note, paid, _amount = self._current_values()
        check = check_payment(self._amount.GetValue(), paid, self._today, self._money_fmt)
        if check.amount_cents is None:
            self._amount.SetFocus()
            return
        cents = check.amount_cents
        if self._run(
            Outcome.PAID,
            lambda: payments.reconcile(
                self._conn,
                self._occ_id,
                paid_date=paid,
                actual_amount_cents=cents,
                note=note,
                today=self._today,
                due_date=due,
            ),
        ):
            self.EndModal(wx.ID_OK)

    def _on_skip(self, _event: wx.CommandEvent) -> None:
        due, note, _paid, _amount = self._current_values()
        dlg = wx.MessageDialog(
            self,
            f"Skip the {self._row.series.payee} payment due {format_date(due)}?\n\n"
            "Use this when it doesn't need paying. It will be listed in Payment History "
            "as skipped, and you can undo it from there.",
            "Skip Payment",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        )
        dlg.SetYesNoLabels("S&kip It", "&Cancel")
        confirmed = dlg.ShowModal() == wx.ID_YES
        dlg.Destroy()
        if confirmed and self._run(
            Outcome.SKIPPED,
            lambda: payments.skip(
                self._conn, self._occ_id, note=note, today=self._today, due_date=due
            ),
        ):
            self.EndModal(wx.ID_OK)

    def _run(self, outcome: Outcome, action: Callable[[], object]) -> bool:
        """Run a service call. On an expected failure, explain it and return False."""
        try:
            action()
        except ValidationError as exc:
            wx.MessageBox(str(exc), "YOMIL", wx.OK | wx.ICON_WARNING, self)
            return False
        except YomilError as exc:
            # The payment changed or vanished underneath us: nothing more to do here,
            # but the main list needs refreshing.
            wx.MessageBox(str(exc), "YOMIL", wx.OK | wx.ICON_WARNING, self)
            self.EndModal(wx.ID_OK)
            return False
        self.outcome = outcome
        return True

    # ------------------------------------------------------------------ close

    def _on_close(self, _event: wx.CommandEvent) -> None:
        due, note, paid, amount = self._current_values()
        i_due, i_note, i_paid, i_amount = self._initial
        record_changed = (due, note) != (i_due, i_note)
        payment_changed = (paid, amount) != (i_paid, i_amount)

        if record_changed:
            message = "Save your changes to the due date and note?"
            if payment_changed:
                message += "\n\nThe paid date and amount are kept only when you choose Mark Paid."
            dlg = wx.MessageDialog(
                self, message, "Unsaved Changes", wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
            )
            dlg.SetYesNoCancelLabels("&Save", "&Don't Save", "&Keep Editing")
            answer = dlg.ShowModal()
            dlg.Destroy()
            if answer == wx.ID_CANCEL or (answer == wx.ID_YES and not self._save()):
                return
        elif payment_changed:
            dlg = wx.MessageDialog(
                self,
                "You changed the payment details but didn't mark it paid.\n\n"
                "Close without marking it paid?",
                "Not Marked Paid",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
            )
            dlg.SetYesNoLabels("&Close", "&Keep Editing")
            answer = dlg.ShowModal()
            dlg.Destroy()
            if answer != wx.ID_YES:
                return
        self.EndModal(wx.ID_OK if self.outcome else wx.ID_CANCEL)
