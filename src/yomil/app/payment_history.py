"""Payment History: the "check register" of paid and skipped payments, newest first.

Opening a row shows it in the Event Viewer, where it can be corrected or marked unpaid.
A plain report ``wx.ListCtrl`` (like Manage Bills), rebuilt after each change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from yomil.app.event_viewer import EventViewer
from yomil.app.lists import apply_list_font, fit_columns
from yomil.core.history import HISTORY_COLUMNS, history_cells
from yomil.core.models import OccurrenceStatus
from yomil.services import bills, payments, settings

if TYPE_CHECKING:
    import sqlite3
    from datetime import date

    from yomil.core.formatting import MoneyFormat
    from yomil.core.models import Occurrence

_AMOUNT_COLUMN = HISTORY_COLUMNS.index("Amount")


class PaymentHistoryDialog(wx.Dialog):
    """Modal. After ``ShowModal()``, :attr:`changed` says whether any payment was changed."""

    def __init__(
        self,
        parent: wx.Window,
        conn: sqlite3.Connection,
        *,
        money_fmt: MoneyFormat,
        today: date,
    ) -> None:
        super().__init__(
            parent,
            title="Payment History",
            size=(860, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._conn = conn
        self._money_fmt = money_fmt
        self._today = today
        self._payments: list[Occurrence] = []
        self.changed = False

        self._list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES)
        for i, title in enumerate(HISTORY_COLUMNS):
            align = wx.LIST_FORMAT_RIGHT if i == _AMOUNT_COLUMN else wx.LIST_FORMAT_LEFT
            self._list.InsertColumn(i, title, align)
        apply_list_font(self._list, settings.list_font_size(conn))
        self._empty_text = wx.StaticText(
            self, label="Nothing here yet. Payments you mark paid or skip will be listed here."
        )

        self._open = wx.Button(self, label="&Open…")
        close = wx.Button(self, wx.ID_CANCEL, label="&Close")
        self._list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_open)  # double-click or Enter
        self._list.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _evt: self._update_buttons())
        self._list.Bind(wx.EVT_LIST_ITEM_DESELECTED, lambda _evt: self._update_buttons())
        self._open.Bind(wx.EVT_BUTTON, self._on_open)

        gap = self.FromDIP(8)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(self._open)
        buttons.AddStretchSpacer()
        buttons.Add(close)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._empty_text, 0, wx.LEFT | wx.RIGHT | wx.TOP, 2 * gap)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, gap)
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, gap)
        self.SetSizer(sizer)
        self.CentreOnParent()

        self._reload()
        self._list.SetFocus()

    def _reload(self, *, select_id: int | None = None, fallback_index: int = 0) -> None:
        """Rebuild the list, selecting payment ``select_id`` or, if it's gone, the row now
        at ``fallback_index`` (so after marking one unpaid she carries on from there).
        """
        self._payments = payments.history(self._conn)
        series = {s.id: s for s in bills.list_all(self._conn)}
        grey = wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)

        self._list.DeleteAllItems()
        for i, occ in enumerate(self._payments):
            cells = history_cells(occ, series[occ.series_id], self._money_fmt)
            self._list.InsertItem(i, cells[0])
            for col, text in enumerate(cells[1:], start=1):
                self._list.SetItem(i, col, text)
            if occ.status is OccurrenceStatus.SKIPPED:
                self._list.SetItemTextColour(i, grey)  # and its Status column says "Skipped"
        fit_columns(self._list)

        if self._payments:
            index = next(
                (i for i, occ in enumerate(self._payments) if occ.id == select_id),
                min(fallback_index, len(self._payments) - 1),
            )
            self._list.Select(index)
            self._list.Focus(index)
            self._list.EnsureVisible(index)
        self._empty_text.Show(not self._payments)
        self._update_buttons()
        self.Layout()

    def _update_buttons(self) -> None:
        self._open.Enable(self._list.GetFirstSelected() >= 0)

    def _on_open(self, _event: wx.Event) -> None:
        index = self._list.GetFirstSelected()
        if not 0 <= index < len(self._payments):
            return
        occ_id = self._payments[index].id
        assert occ_id is not None
        dlg = EventViewer(self, self._conn, occ_id, money_fmt=self._money_fmt, today=self._today)
        changed = dlg.ShowModal() == wx.ID_OK
        dlg.Destroy()
        if changed:
            self.changed = True
            self._reload(select_id=occ_id, fallback_index=index)
        self._list.SetFocus()
