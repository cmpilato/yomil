"""Event Viewer: one paid or skipped payment, read-only, with buttons to correct it.

Opened from Payment History. Edit… (paid payments only) opens the Payment Editor;
Mark Unpaid… / Undo Skip… puts the payment back on the main list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from yomil.app.fields import grow_to_fit
from yomil.app.fonts import inherit_font
from yomil.app.payment_editor import PaymentEditor
from yomil.core.errors import YomilError
from yomil.core.history import bill_name, payment_details, unresolve_question
from yomil.core.models import OccurrenceStatus
from yomil.services import bills, payments

if TYPE_CHECKING:
    import sqlite3
    from datetime import date

    from yomil.core.formatting import MoneyFormat


class EventViewer(wx.Dialog):
    """Modal. After ``ShowModal()``, :attr:`changed` says whether the payment was changed."""

    def __init__(
        self,
        parent: wx.Window,
        conn: sqlite3.Connection,
        occurrence_id: int,
        *,
        money_fmt: MoneyFormat,
        today: date,
    ) -> None:
        super().__init__(parent, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        inherit_font(self, parent)  # before creating any controls
        self._conn = conn
        self._occ_id = occurrence_id
        self._money_fmt = money_fmt
        self._today = today
        self.changed = False
        self._load()
        self.SetTitle(f"Payment: {bill_name(self._occ, self._series)}")

        title = wx.StaticText(self, label=bill_name(self._occ, self._series))
        title.SetFont(self.GetFont().Bold().Scaled(1.4))
        self._details = wx.FlexGridSizer(cols=2, vgap=self.FromDIP(4), hgap=self.FromDIP(12))
        self._fill_details()

        gap = 2 * self.FromDIP(8)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.TOP, gap)
        sizer.Add(self._details, 1, wx.EXPAND | wx.ALL, gap)
        sizer.Add(self._build_buttons(), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, gap)
        self.SetSizerAndFit(sizer)
        self.SetMinSize(self.GetSize())
        self.CentreOnParent()
        self._close.SetFocus()  # GTK's Enter presses the focused button, not the default

    def _load(self) -> None:
        self._occ = payments.get(self._conn, self._occ_id)
        self._series = bills.get(self._conn, self._occ.series_id)

    def _fill_details(self) -> None:
        self._details.Clear(delete_windows=True)
        for label, value in payment_details(self._occ, self._series, self._money_fmt):
            text = wx.StaticText(self, label=value)
            text.Wrap(self.FromDIP(420))
            self._details.Add(wx.StaticText(self, label=label))
            self._details.Add(text)

    def _build_buttons(self) -> wx.Sizer:
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        gap = self.FromDIP(8)
        if self._occ.status is OccurrenceStatus.PAID:
            edit = wx.Button(self, label="&Edit…")
            edit.Bind(wx.EVT_BUTTON, self._on_edit)
            sizer.Add(edit, 0, wx.RIGHT, gap)
            undo = wx.Button(self, label="Mark &Unpaid…")
        else:
            undo = wx.Button(self, label="&Undo Skip…")
        undo.Bind(wx.EVT_BUTTON, self._on_unresolve)
        sizer.Add(undo)
        sizer.AddStretchSpacer()
        sizer.AddSpacer(4 * gap)
        close = self._close = wx.Button(self, wx.ID_CANCEL, label="&Close")  # also Escape
        close.SetDefault()  # just looking: Enter closes, nothing changes by accident
        close.Bind(wx.EVT_BUTTON, lambda _evt: self._end())
        sizer.Add(close)
        return sizer

    # ---------------------------------------------------------------- actions

    def _on_edit(self, _event: wx.CommandEvent) -> None:
        dlg = PaymentEditor(
            self, self._conn, self._occ, self._series, money_fmt=self._money_fmt, today=self._today
        )
        saved = dlg.ShowModal() == wx.ID_OK
        dlg.Destroy()
        if not saved:
            return
        self.changed = True
        try:
            self._load()
        except YomilError as exc:
            self._show_error(str(exc))
            self._end()
            return
        if not self._occ.resolved:  # marked unpaid elsewhere in the meantime
            self._end()
            return
        self._fill_details()
        grow_to_fit(self)

    def _on_unresolve(self, _event: wx.CommandEvent) -> None:
        paid = self._occ.status is OccurrenceStatus.PAID
        dlg = wx.MessageDialog(
            self,
            unresolve_question(self._occ, self._series),
            "Mark Unpaid" if paid else "Undo Skip",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        )
        dlg.SetYesNoLabels("Mark &Unpaid" if paid else "&Undo Skip", "&Cancel")
        confirmed = dlg.ShowModal() == wx.ID_YES
        dlg.Destroy()
        if not confirmed:
            return
        try:
            payments.unreconcile(self._conn, self._occ_id)
        except YomilError as exc:
            self._show_error(str(exc))
        self.changed = True
        self._end()

    def _end(self) -> None:
        self.EndModal(wx.ID_OK if self.changed else wx.ID_CANCEL)

    def _show_error(self, message: str) -> None:
        wx.MessageBox(message, "YOMIL", wx.OK | wx.ICON_WARNING, self)
