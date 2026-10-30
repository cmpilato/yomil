"""Correct a paid payment's paid date, amount, or note (from the Event Viewer's Edit…).

Same field rules as the Event Editor (``core.payment_form``), shown next to the fields.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
import wx.adv

from yomil.app.dates import from_wx, to_wx
from yomil.app.fields import grow_to_fit, show_message
from yomil.app.fonts import inherit_font
from yomil.core.errors import ValidationError, YomilError
from yomil.core.formatting import format_date, format_money_for_entry
from yomil.core.history import bill_name
from yomil.core.payment_form import check_payment
from yomil.services import payments

if TYPE_CHECKING:
    import sqlite3
    from datetime import date

    from yomil.core.formatting import MoneyFormat
    from yomil.core.models import Occurrence, Series


class PaymentEditor(wx.Dialog):
    """Modal. Returns ``wx.ID_OK`` from ``ShowModal()`` if it saved a change."""

    def __init__(
        self,
        parent: wx.Window,
        conn: sqlite3.Connection,
        occ: Occurrence,
        series: Series,
        *,
        money_fmt: MoneyFormat,
        today: date,
    ) -> None:
        name = bill_name(occ, series)
        super().__init__(
            parent, title=f"Edit Payment: {name}", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        inherit_font(self, parent)  # before creating any controls
        assert occ.id is not None
        assert occ.paid_date is not None
        self._conn = conn
        self._occ_id = occ.id
        self._money_fmt = money_fmt
        self._today = today

        title = wx.StaticText(self, label=name)
        title.SetFont(self.GetFont().Bold().Scaled(1.4))
        due = wx.StaticText(self, label=f"Due {format_date(occ.due_date)}")

        picker_style = wx.adv.DP_DROPDOWN | wx.adv.DP_SHOWCENTURY
        self._paid = wx.adv.DatePickerCtrl(self, dt=to_wx(occ.paid_date), style=picker_style)
        self._paid_msg = wx.StaticText(self)
        amount = occ.actual_amount_cents
        self._amount = wx.TextCtrl(
            self, value="" if amount is None else format_money_for_entry(amount, money_fmt)
        )
        self._amount_msg = wx.StaticText(self)
        self._note = wx.TextCtrl(
            self, value=occ.note or "", style=wx.TE_MULTILINE, size=self.FromDIP(wx.Size(-1, 70))
        )
        self._paid.Bind(wx.adv.EVT_DATE_CHANGED, lambda _evt: self._update_checks())
        self._amount.Bind(wx.EVT_TEXT, lambda _evt: self._update_checks())

        grid = wx.FlexGridSizer(cols=2, vgap=self.FromDIP(4), hgap=self.FromDIP(12))
        grid.AddGrowableCol(1)
        grid.AddGrowableRow(4)  # the note grows with the dialog
        label_flags = wx.ALIGN_CENTER_VERTICAL
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

        self._save_button = wx.Button(self, wx.ID_SAVE, label="&Save")
        cancel = wx.Button(self, wx.ID_CANCEL, label="&Cancel")  # also Escape and the X
        self._save_button.SetDefault()
        self._save_button.Bind(wx.EVT_BUTTON, self._on_save)
        cancel.Bind(wx.EVT_BUTTON, self._on_cancel)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(self._save_button)
        buttons.AddStretchSpacer()
        buttons.Add(cancel)

        gap = 2 * self.FromDIP(8)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP, gap)
        sizer.Add(due, 0, wx.LEFT | wx.RIGHT, gap)
        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, gap)
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, gap)
        self.SetSizerAndFit(sizer)
        self.SetMinSize(self.GetSize())
        self.CentreOnParent()

        self._initial = self._current_values()
        self._update_checks()
        self._amount.SetFocus()
        self._amount.SelectAll()

    def _current_values(self) -> tuple[date, str, str]:
        return (
            from_wx(self._paid.GetValue()),
            self._amount.GetValue().strip(),
            self._note.GetValue().strip(),
        )

    def _update_checks(self) -> None:
        check = check_payment(
            self._amount.GetValue(), from_wx(self._paid.GetValue()), self._today, self._money_fmt
        )
        show_message(self._amount_msg, check.amount_message)
        show_message(self._paid_msg, check.paid_date_message)
        self._save_button.Enable(check.can_mark_paid)
        grow_to_fit(self)

    def _on_save(self, _event: wx.CommandEvent) -> None:
        if self._current_values() == self._initial:
            self.EndModal(wx.ID_CANCEL)  # nothing to save
        elif self._save():
            self.EndModal(wx.ID_OK)

    def _save(self) -> bool:
        paid, _amount, note = self._current_values()
        check = check_payment(self._amount.GetValue(), paid, self._today, self._money_fmt)
        if check.amount_cents is None:
            self._amount.SetFocus()
            return False
        try:
            payments.edit_reconciled(
                self._conn,
                self._occ_id,
                paid_date=paid,
                actual_amount_cents=check.amount_cents,
                note=note,
            )
        except ValidationError as exc:
            wx.MessageBox(str(exc), "YOMIL", wx.OK | wx.ICON_WARNING, self)
            return False
        except YomilError as exc:
            # Changed underneath us (e.g. marked unpaid elsewhere): nothing left to edit.
            wx.MessageBox(str(exc), "YOMIL", wx.OK | wx.ICON_WARNING, self)
            self.EndModal(wx.ID_OK)
            return False
        return True

    def _on_cancel(self, _event: wx.CommandEvent) -> None:
        if self._current_values() != self._initial:
            dlg = wx.MessageDialog(
                self,
                "Save your changes to this payment?",
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
