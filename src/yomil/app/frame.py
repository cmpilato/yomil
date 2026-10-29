"""Main window: the list of bills to pay, with menus and action buttons.

With a tray icon, closing the window hides it and the tray menu's Quit really exits.
Without one (``--no-tray`` or no tray available), closing the window quits the app.

The list is rebuilt from ``services.payments`` whenever the date may have changed: when
the window is shown or activated, at local midnight, and after every change.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

import wx

from yomil.app.bill_list import BillListCtrl
from yomil.app.event_editor import EventEditor, Outcome
from yomil.app.manage_bills import ManageBillsDialog
from yomil.app.tray import TrayIcon, make_icon
from yomil.core.errors import YomilError
from yomil.core.formatting import format_date, format_money, quick_pay_amount, summary_text
from yomil.core.models import AmountKind
from yomil.services import bills, payments, settings

if TYPE_CHECKING:
    import sqlite3

    from yomil.core.formatting import MoneyFormat
    from yomil.core.main_list import BillRow

log = logging.getLogger(__name__)

_PAGE_LIST, _PAGE_EMPTY = 0, 1
_MIDNIGHT_SLACK = timedelta(seconds=5)  # fire just after midnight, never just before

_ID_EXPORT = wx.NewIdRef()
_ID_MANAGE_BILLS = wx.NewIdRef()
_ID_HISTORY = wx.NewIdRef()


def _today() -> date:
    return date.today()  # noqa: DTZ011  (bills are due on local calendar dates)


class MainFrame(wx.Frame):
    def __init__(
        self, conn: sqlite3.Connection, *, money_fmt: MoneyFormat, use_tray: bool = True
    ) -> None:
        super().__init__(None, title="YOMIL", size=(900, 520))
        self._conn = conn
        self._money_fmt = money_fmt
        self._today = _today()
        self.SetIcon(make_icon())
        self._tray: TrayIcon | None = TrayIcon(self) if use_tray else None

        self._build_menus()
        self._build_body()
        self.CreateStatusBar()

        self._midnight_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_midnight, self._midnight_timer)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_ACTIVATE, self._on_activate)

        self.refresh()
        self._arm_midnight_timer()

    # ------------------------------------------------------------------ layout

    def _build_menus(self) -> None:
        file_menu = wx.Menu()
        file_menu.Append(_ID_EXPORT, "&Export…")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit")

        bills_menu = wx.Menu()
        bills_menu.Append(_ID_MANAGE_BILLS, "&Manage Bills…")
        bills_menu.Append(_ID_HISTORY, "Payment &History…")

        tools_menu = wx.Menu()
        tools_menu.Append(wx.ID_PREFERENCES, "&Preferences…")

        menu_bar = wx.MenuBar()
        menu_bar.Append(file_menu, "&File")
        menu_bar.Append(bills_menu, "&Bills")
        menu_bar.Append(tools_menu, "&Tools")
        self.SetMenuBar(menu_bar)

        # Not built yet (Phases 5-7).
        for item_id in (_ID_EXPORT, _ID_HISTORY, wx.ID_PREFERENCES):
            menu_bar.Enable(item_id, False)

        self.Bind(wx.EVT_MENU, lambda _evt: self.quit(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self._on_manage_bills, id=_ID_MANAGE_BILLS)

    def _build_body(self) -> None:
        panel = self._panel = wx.Panel(self)
        self._book = wx.Simplebook(panel)

        self._list = BillListCtrl(self._book, self._money_fmt)
        self._list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_open)  # double-click or Enter
        self._list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_selection_changed)
        self._list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_selection_changed)
        self._book.AddPage(self._list, "list")

        empty = wx.Panel(self._book)
        self._empty_text = wx.StaticText(empty, style=wx.ALIGN_CENTRE_HORIZONTAL)
        manage = wx.Button(empty, label="&Manage Bills…")
        manage.Bind(wx.EVT_BUTTON, self._on_manage_bills)
        empty_sizer = wx.BoxSizer(wx.VERTICAL)
        empty_sizer.AddStretchSpacer()
        empty_sizer.Add(self._empty_text, 0, wx.EXPAND | wx.ALL, self.FromDIP(20))
        empty_sizer.Add(manage, 0, wx.ALIGN_CENTER_HORIZONTAL)
        empty_sizer.AddStretchSpacer()
        empty.SetSizer(empty_sizer)
        self._book.AddPage(empty, "empty")

        self._open_button = wx.Button(panel, label="&Open…")
        self._pay_button = wx.Button(panel, label="Mark &Paid")
        self._open_button.Bind(wx.EVT_BUTTON, self._on_open)
        self._pay_button.Bind(wx.EVT_BUTTON, self._on_mark_paid)

        gap = self.FromDIP(8)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(self._open_button, 0, wx.RIGHT, gap)
        buttons.Add(self._pay_button)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._book, 1, wx.EXPAND | wx.ALL, gap)
        sizer.Add(buttons, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, gap)
        panel.SetSizer(sizer)

    # ----------------------------------------------------------------- refresh

    def refresh(self, *, select_index: int | None = None) -> None:
        """Rebuild the list for today.

        Keeps the same bill selected, or with ``select_index``, whatever row is now at
        that position (after paying a bill, so she can carry on down the list).
        """
        previous = self._list.selected_row()
        self._today = _today()
        try:
            payments.materialize(self._conn, self._today)
            rows = payments.main_list(self._conn, self._today)
            any_bills = any(s.active for s in bills.list_all(self._conn))
            font_size = settings.list_font_size(self._conn)
        except Exception:
            log.exception("Could not load the bill list")
            self._show_error("YOMIL could not load your bills. Details are in the log file.")
            return

        self._list.apply_font(font_size)
        self._list.set_rows(rows, self._today)
        self._grow_to_fit_list()
        self.SetStatusText(summary_text(rows))
        if rows:
            self._book.SetSelection(_PAGE_LIST)
            if select_index is None:
                select_index = self._index_of(rows, previous)
            self._list.select(select_index)
        else:
            self._empty_text.SetLabel(
                "Nothing to pay right now."
                if any_bills
                else "You don't have any bills yet. Add one with Manage Bills."
            )
            self._book.SetSelection(_PAGE_EMPTY)
            self._book.GetPage(_PAGE_EMPTY).Layout()
        self._update_buttons()

    def _grow_to_fit_list(self) -> None:
        """Widen the window (never past the screen) so large fonts don't need scrolling."""
        self.Layout()  # the first refresh runs before the sizers ever have
        self._panel.Layout()
        extra = self._list.extra_width_needed()
        if not extra or self.IsMaximized():
            return
        screen = wx.Display(self).GetClientArea()
        width = min(self.GetSize().width + extra, screen.width)
        self.SetSize(width, self.GetSize().height)
        if self.GetRect().right > screen.right:
            self.Move(max(screen.left, screen.right - width), self.GetPosition().y)

    @staticmethod
    def _index_of(rows: list[BillRow], previous: BillRow | None) -> int:
        if previous is not None:
            for i, row in enumerate(rows):
                if row.series.id == previous.series.id:
                    return i
        return 0

    def _update_buttons(self) -> None:
        row = self._list.selected_row()
        self._open_button.Enable(row is not None)
        self._pay_button.Enable(row is not None and quick_pay_amount(row) is not None)

    def _arm_midnight_timer(self) -> None:
        now = datetime.now()  # noqa: DTZ005  (local wall clock is the point)
        midnight = datetime.combine(now.date() + timedelta(days=1), time())
        delay = midnight - now + _MIDNIGHT_SLACK
        self._midnight_timer.StartOnce(int(delay.total_seconds() * 1000))

    # ---------------------------------------------------------------- commands

    def _on_open(self, _event: wx.Event) -> None:
        row = self._list.selected_row()
        if row is None:
            return
        index = self._list.selected_index()
        dlg = EventEditor(self, self._conn, row, money_fmt=self._money_fmt, today=_today())
        dlg.ShowModal()
        outcome = dlg.outcome
        dlg.Destroy()
        # Paid or skipped: the next row moves up into this spot, so carry on from there.
        resolved = outcome in (Outcome.PAID, Outcome.SKIPPED)
        self.refresh(select_index=index if resolved else None)

    def _on_manage_bills(self, _event: wx.Event) -> None:
        dlg = ManageBillsDialog(self, self._conn, money_fmt=self._money_fmt, today=_today())
        dlg.ShowModal()
        dlg.Destroy()
        self.refresh()

    def _on_mark_paid(self, _event: wx.Event) -> None:
        row = self._list.selected_row()
        amount = None if row is None else quick_pay_amount(row)
        if row is None or amount is None:
            return
        assert row.occurrence.id is not None
        today = _today()
        message = (
            f"Mark {row.series.payee} as paid?\n\n"
            f"Due:\t{format_date(row.occurrence.due_date)}\n"
            f"Paid:\t{format_date(today)} (today)\n"
            f"Amount:\t{format_money(amount, self._money_fmt)}"
        )
        if row.series.amount_kind is not AmountKind.FIXED:
            message += "\n\nThat is the expected amount. To enter a different one, use Open…"
        dlg = wx.MessageDialog(self, message, "Mark Paid", wx.YES_NO | wx.ICON_QUESTION)
        dlg.SetYesNoLabels("&Mark Paid", "&Cancel")
        confirmed = dlg.ShowModal() == wx.ID_YES
        dlg.Destroy()
        if not confirmed:
            return

        index = self._list.selected_index()
        try:
            payments.reconcile(
                self._conn,
                row.occurrence.id,
                paid_date=today,
                actual_amount_cents=amount,
                note=row.occurrence.note,
                today=today,
            )
        except YomilError as exc:
            self._show_error(str(exc))
        self.refresh(select_index=index)

    def _show_error(self, message: str) -> None:
        wx.MessageBox(message, "YOMIL", wx.OK | wx.ICON_WARNING, self)

    # ------------------------------------------------------------------ events

    def _on_selection_changed(self, event: wx.ListEvent) -> None:
        self._update_buttons()
        event.Skip()

    def _on_activate(self, event: wx.ActivateEvent) -> None:
        # Catches a missed midnight (e.g. the PC was asleep) as soon as she comes back.
        if event.GetActive() and _today() != self._today:
            wx.CallAfter(self.refresh)
        event.Skip()

    def _on_midnight(self, _event: wx.TimerEvent) -> None:
        self.refresh()
        self._arm_midnight_timer()

    # ---------------------------------------------------------- show and close

    def show_window(self) -> None:
        self.refresh()
        self.Show()
        self.Iconize(False)
        self.Raise()
        self._list.SetFocus()

    def quit(self) -> None:
        self._midnight_timer.Stop()
        self._destroy_tray()
        self.Destroy()

    def _destroy_tray(self) -> None:
        if self._tray is not None:
            self._tray.Destroy()
            self._tray = None

    def _on_close(self, event: wx.CloseEvent) -> None:
        if self._tray is not None and event.CanVeto():
            self.Hide()  # keep running in the tray
            event.Veto()
        else:
            self._midnight_timer.Stop()
            self._destroy_tray()
            event.Skip()  # let the window (and, being the last one, the app) close
