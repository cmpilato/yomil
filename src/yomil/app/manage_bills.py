"""Manage Bills: every bill, active first, with Add / Edit / Retire / Delete.

Unlike the main window's virtual list, this is a plain report ``wx.ListCtrl``: a few
dozen rows at most, so it is simply rebuilt item by item after each change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from yomil.app.bill_editor import BillEditor
from yomil.core.errors import YomilError
from yomil.core.formatting import format_amount, format_date
from yomil.core.schedule import describe, parse_schedule
from yomil.services import bills, payments, settings

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable
    from datetime import date

    from yomil.core.formatting import MoneyFormat
    from yomil.core.models import Series

COLUMNS = ("Bill", "Schedule", "Amount", "Next due", "Status")


class ManageBillsDialog(wx.Dialog):
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
            title="Manage Bills",
            size=(860, 460),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._conn = conn
        self._money_fmt = money_fmt
        self._today = today
        self._bills: list[Series] = []

        self._list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES)
        for i, title in enumerate(COLUMNS):
            self._list.InsertColumn(i, title)
        size = settings.list_font_size(conn)
        if size is not None:
            font = self._list.GetFont()
            font.SetPointSize(size)
            self._list.SetFont(font)

        self._add = wx.Button(self, label="&Add…")
        self._edit = wx.Button(self, label="&Edit…")
        self._retire = wx.Button(self, label="&Retire")
        self._delete = wx.Button(self, label="&Delete…")
        close = wx.Button(self, wx.ID_CANCEL, label="&Close")

        self._list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_edit)
        self._list.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _evt: self._update_buttons())
        self._list.Bind(wx.EVT_LIST_ITEM_DESELECTED, lambda _evt: self._update_buttons())
        self._list.Bind(wx.EVT_LIST_KEY_DOWN, self._on_list_key)
        self._add.Bind(wx.EVT_BUTTON, self._on_add)
        self._edit.Bind(wx.EVT_BUTTON, self._on_edit)
        self._retire.Bind(wx.EVT_BUTTON, self._on_retire)
        self._delete.Bind(wx.EVT_BUTTON, self._on_delete)

        gap = self.FromDIP(8)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        for button in (self._add, self._edit, self._retire, self._delete):
            buttons.Add(button, 0, wx.RIGHT, gap)
        buttons.AddStretchSpacer()
        buttons.Add(close)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, gap)
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, gap)
        self.SetSizer(sizer)
        self.CentreOnParent()

        self._reload()
        self._list.SetFocus()

    # ------------------------------------------------------------------- list

    def _reload(self, select_id: int | None = None) -> None:
        """Rebuild the list, selecting bill ``select_id`` (or keeping the selection)."""
        if select_id is None and (current := self._selected()) is not None:
            select_id = current.id
        self._bills = bills.list_all(self._conn)
        next_due = {
            row.series.id: row.occurrence.due_date
            for row in payments.main_list(self._conn, self._today)
        }
        grey = wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)

        self._list.DeleteAllItems()
        for i, s in enumerate(self._bills):
            due = next_due.get(s.id)
            cells = (
                s.payee,
                describe(parse_schedule(s.rrule, s.dtstart), s.dtstart),
                format_amount(s.expected_amount_cents, s.amount_kind, self._money_fmt),
                "—" if due is None else format_date(due),
                "Active" if s.active else "Retired",
            )
            self._list.InsertItem(i, cells[0])
            for col, text in enumerate(cells[1:], start=1):
                self._list.SetItem(i, col, text)
            if not s.active:
                self._list.SetItemTextColour(i, grey)

        for col in range(len(COLUMNS)):
            # The wider of the header and the widest cell.
            self._list.SetColumnWidth(col, wx.LIST_AUTOSIZE)
            cells_width = self._list.GetColumnWidth(col)
            self._list.SetColumnWidth(col, wx.LIST_AUTOSIZE_USEHEADER)
            if self._list.GetColumnWidth(col) < cells_width:
                self._list.SetColumnWidth(col, cells_width)

        index = next((i for i, s in enumerate(self._bills) if s.id == select_id), 0)
        if self._bills:
            self._list.Select(index)
            self._list.Focus(index)
        self._update_buttons()

    def _selected(self) -> Series | None:
        i = self._list.GetFirstSelected()
        return self._bills[i] if 0 <= i < len(self._bills) else None

    def _update_buttons(self) -> None:
        s = self._selected()
        for button in (self._edit, self._retire, self._delete):
            button.Enable(s is not None)
        self._retire.SetLabel("&Reactivate" if s is not None and not s.active else "&Retire")
        self.Layout()

    # ---------------------------------------------------------------- actions

    def _on_add(self, _event: wx.CommandEvent) -> None:
        self._open_editor(None)

    def _on_edit(self, _event: wx.Event) -> None:
        s = self._selected()
        if s is not None:
            self._open_editor(s)

    def _open_editor(self, base: Series | None) -> None:
        dlg = BillEditor(self, self._conn, base, money_fmt=self._money_fmt, today=self._today)
        saved = dlg.saved if dlg.ShowModal() == wx.ID_OK else None
        dlg.Destroy()
        self._reload(select_id=saved.id if saved else None)

    def _on_retire(self, _event: wx.CommandEvent) -> None:
        s = self._selected()
        if s is None or s.id is None:
            return
        try:
            if s.active:
                bills.retire(self._conn, s.id)
            else:
                bills.reactivate(self._conn, s.id, today=self._today)
        except YomilError as exc:
            self._show_error(str(exc))
        self._reload(select_id=s.id)

    def _on_delete(self, _event: wx.CommandEvent) -> None:
        s = self._selected()
        if s is None or s.id is None:
            return
        sid = s.id
        if bills.can_delete(self._conn, sid):
            if self._ask(f"Delete {s.payee}?\n\nThis can't be undone.", "Delete Bill", "&Delete"):
                self._run(lambda: bills.delete(self._conn, sid))
        elif s.active:
            if self._ask(
                f"{s.payee} has payment history, so it can't be deleted.\n\n"
                "Retire it instead? Retired bills leave the main list but keep their "
                "history, and you can reactivate them later.",
                "Delete Bill",
                "&Retire It",
            ):
                self._run(lambda: bills.retire(self._conn, sid))
        else:
            wx.MessageBox(
                f"{s.payee} has payment history, so it can't be deleted. "
                "It's already retired, so it won't appear on the main list.",
                "Delete Bill",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )

    def _on_list_key(self, event: wx.ListEvent) -> None:
        if event.GetKeyCode() == wx.WXK_DELETE:
            self._on_delete(event)
        else:
            event.Skip()

    def _ask(self, message: str, title: str, yes_label: str) -> bool:
        dlg = wx.MessageDialog(self, message, title, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        dlg.SetYesNoLabels(yes_label, "&Cancel")
        confirmed = dlg.ShowModal() == wx.ID_YES
        dlg.Destroy()
        return bool(confirmed)

    def _run(self, action: Callable[[], object]) -> None:
        try:
            action()
        except YomilError as exc:
            self._show_error(str(exc))
        self._reload()

    def _show_error(self, message: str) -> None:
        wx.MessageBox(message, "YOMIL", wx.OK | wx.ICON_WARNING, self)
