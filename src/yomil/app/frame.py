"""Main window: the list of bills to pay, with menus and action buttons.

With a tray icon, closing the window hides it and the tray menu's Quit really exits.
Without one (``--no-tray`` or no tray available), closing the window quits the app.

The list is rebuilt from ``services.payments`` whenever the date may have changed: when
the window is shown or activated, at local midnight, and after every change. Each
refresh also updates the tray icon and shows any reminders that are due; a timer checks
again every few minutes, so reminders held back overnight appear in the morning.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import wx
import wx.adv

from yomil import __version__
from yomil.app.bill_list import BillListCtrl
from yomil.app.event_editor import EventEditor, Outcome
from yomil.app.fonts import set_font_everywhere, ui_font
from yomil.app.manage_bills import ManageBillsDialog
from yomil.app.notify import Notifier
from yomil.app.payment_history import PaymentHistoryDialog
from yomil.app.preferences import PreferencesDialog
from yomil.app.tray import TrayIcon, app_icons
from yomil.core.formatting import summary_text
from yomil.core.reminders import in_quiet_hours, notices
from yomil.core.urgency import Urgency
from yomil.paths import log_dir
from yomil.services import bills, export, payments, reminders, settings

if TYPE_CHECKING:
    import sqlite3

    from yomil.core.formatting import MoneyFormat
    from yomil.core.main_list import BillRow

log = logging.getLogger(__name__)

_PAGE_LIST, _PAGE_EMPTY = 0, 1
_MIDNIGHT_SLACK = timedelta(seconds=5)  # fire just after midnight, never just before
_REMINDER_CHECK_MS = 15 * 60 * 1000

_ID_EXPORT = wx.NewIdRef()
_ID_MANAGE_BILLS = wx.NewIdRef()
_ID_HISTORY = wx.NewIdRef()


def _today() -> date:
    return date.today()  # noqa: DTZ011  (bills are due on local calendar dates)


class MainFrame(wx.Frame):
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        money_fmt: MoneyFormat,
        use_tray: bool = True,
        db_path: Path | None = None,
    ) -> None:
        super().__init__(None, title="YOMIL", size=(900, 520))
        self._conn = conn
        self._db_path = db_path
        self._money_fmt = money_fmt
        self._today = _today()
        self._font_size_applied: tuple[int | None] | None = None
        self.SetIcons(app_icons())
        self._tray: TrayIcon | None = TrayIcon(self) if use_tray else None
        self._notifier = Notifier(self, self._tray)

        self._build_menus()
        self._build_body()
        self.CreateStatusBar()

        self._midnight_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_midnight, self._midnight_timer)
        self._reminder_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda _evt: self._show_reminders(), self._reminder_timer)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_ACTIVATE, self._on_activate)

        self.refresh()
        self._arm_midnight_timer()
        self._reminder_timer.Start(_REMINDER_CHECK_MS)

    # ------------------------------------------------------------------ layout

    def _build_menus(self) -> None:
        file_menu = wx.Menu()
        file_menu.Append(_ID_EXPORT, "&Export Payment History…")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit")

        bills_menu = wx.Menu()
        bills_menu.Append(_ID_MANAGE_BILLS, "&Manage Bills…")
        bills_menu.Append(_ID_HISTORY, "Payment &History…")

        tools_menu = wx.Menu()
        tools_menu.Append(wx.ID_PREFERENCES, "&Preferences…")

        help_menu = wx.Menu()
        help_menu.Append(wx.ID_ABOUT, "&About YOMIL…")

        menu_bar = wx.MenuBar()
        menu_bar.Append(file_menu, "&File")
        menu_bar.Append(bills_menu, "&Bills")
        menu_bar.Append(tools_menu, "&Tools")
        menu_bar.Append(help_menu, "&Help")
        self.SetMenuBar(menu_bar)

        self.Bind(wx.EVT_MENU, lambda _evt: self.quit(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self._on_manage_bills, id=_ID_MANAGE_BILLS)
        self.Bind(wx.EVT_MENU, self._on_history, id=_ID_HISTORY)
        self.Bind(wx.EVT_MENU, self._on_export, id=_ID_EXPORT)
        self.Bind(wx.EVT_MENU, self._on_preferences, id=wx.ID_PREFERENCES)
        self.Bind(wx.EVT_MENU, self._on_about, id=wx.ID_ABOUT)

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
        self._open_button.Bind(wx.EVT_BUTTON, self._on_open)

        gap = self.FromDIP(8)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(self._open_button)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._book, 1, wx.EXPAND | wx.ALL, gap)
        sizer.Add(buttons, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, gap)
        panel.SetSizer(sizer)

    # ----------------------------------------------------------------- refresh

    def refresh(self, *, select_index: int | None = None) -> None:
        """Rebuild the list for today.

        Keeps the same bill selected, or with ``select_index``, whatever row is now at
        that position (after paying a bill, so the user can carry on down the list).
        """
        previous = self._list.selected_row()
        self._today = _today()
        try:
            payments.materialize(self._conn, self._today)
            rows = payments.main_list(self._conn, self._today)
            any_bills = any(s.active for s in bills.list_all(self._conn))
            font_size = settings.font_size(self._conn)
        except Exception:
            log.exception("Could not load the bill list")
            self._show_error("YOMIL could not load your bills. Details are in the log file.")
            return

        self._apply_font_size(font_size)
        self._list.set_rows(rows, self._today)
        self._grow_to_fit_list()
        self.SetStatusText(summary_text(rows))
        if self._tray is not None:
            overdue = sum(1 for r in rows if r.urgency is Urgency.OVERDUE)
            self._tray.update(summary_text(rows), overdue)
        if rows:
            self._book.SetSelection(_PAGE_LIST)
            if select_index is None and previous is not None:
                select_index = self._index_of(rows, previous)
            if select_index is None:
                self._list.focus(0)  # selecting is left to the user
            else:
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
        self._show_reminders()

    def _show_reminders(self) -> None:
        """Show any reminders that are due (each only once; none overnight)."""
        now = datetime.now()  # noqa: DTZ005  (local wall clock is the point)
        try:
            if not settings.reminders_enabled(self._conn) or in_quiet_hours(now.time()):
                return
            due = reminders.due(self._conn, now.date(), self._money_fmt)
            for notice in notices(due):
                if self._notifier.show(notice, self.show_bill):
                    reminders.mark_shown(self._conn, notice.reminders)
        except Exception:
            log.exception("Could not show reminders")  # never worth interrupting the user for

    def _apply_font_size(self, points: int | None) -> None:
        """Re-font the whole window if the text size setting changed (it starts out unset)."""
        if self._font_size_applied == (points,):
            return
        self._font_size_applied = (points,)
        font = ui_font(points)
        set_font_everywhere(self, font)
        self._list.apply_font(font)
        self._panel.Layout()

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
    def _index_of(rows: list[BillRow], previous: BillRow) -> int:
        for i, row in enumerate(rows):
            if row.series.id == previous.series.id:
                return i
        return 0

    def _update_buttons(self) -> None:
        row = self._list.selected_row()
        self._open_button.Enable(row is not None)

    def _arm_midnight_timer(self) -> None:
        now = datetime.now()  # noqa: DTZ005  (local wall clock is the point)
        midnight = datetime.combine(now.date() + timedelta(days=1), time())
        delay = midnight - now + _MIDNIGHT_SLACK
        self._midnight_timer.StartOnce(int(delay.total_seconds() * 1000))

    # ---------------------------------------------------------------- commands

    def _on_open(self, event: wx.Event) -> None:
        if isinstance(event, wx.ListEvent):  # Enter works on a focused, unselected row too
            self._list.select(event.GetIndex())
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

    def _on_history(self, _event: wx.Event) -> None:
        dlg = PaymentHistoryDialog(self, self._conn, money_fmt=self._money_fmt, today=_today())
        dlg.ShowModal()
        dlg.Destroy()
        self.refresh()  # a payment marked unpaid is back on the list

    def _on_export(self, _event: wx.Event) -> None:
        dlg = wx.FileDialog(
            self,
            "Export Payment History",
            defaultDir=wx.StandardPaths.Get().GetDocumentsDir(),
            defaultFile=f"YOMIL payment history {_today().isoformat()}.csv",
            wildcard="Spreadsheet (CSV) files (*.csv)|*.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        chosen = dlg.ShowModal() == wx.ID_OK
        path = Path(dlg.GetPath())
        dlg.Destroy()
        if not chosen:
            return
        if path.suffix.lower() != ".csv":
            path = path.with_name(path.name + ".csv")
        try:
            count = export.write_history_csv(self._conn, path)
        except OSError as exc:
            log.exception("Could not export the payment history")
            self._show_error(f"YOMIL couldn't save the file.\n\n{exc.strerror or exc}")
            return
        wx.MessageBox(
            f"Saved {count} {'payment' if count == 1 else 'payments'} to:\n\n{path}\n\n"
            "It opens in Excel or any spreadsheet program.",
            "Export Payment History",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _on_preferences(self, _event: wx.Event) -> None:
        dlg = PreferencesDialog(self, self._conn, money_fmt=self._money_fmt, today=_today())
        dlg.ShowModal()
        dlg.Destroy()
        self.refresh()  # new text size and colors, right away

    def _on_about(self, _event: wx.Event) -> None:
        info = wx.adv.AboutDialogInfo()
        info.SetName("YOMIL")
        info.SetVersion(__version__)
        info.SetIcon(self.GetIcon())
        lines = ["Your Obligations, Monitored, Informed, Logged.", "Bill reminders and records."]
        if self._db_path is not None:
            lines += ["", f"Your data: {self._db_path.parent}"]
        lines.append(f"Log files: {log_dir()}")
        info.SetDescription("\n".join(lines))
        wx.adv.AboutBox(info, self)

    def _show_error(self, message: str) -> None:
        wx.MessageBox(message, "YOMIL", wx.OK | wx.ICON_WARNING, self)

    # ------------------------------------------------------------------ events

    def _on_selection_changed(self, event: wx.ListEvent) -> None:
        self._update_buttons()
        event.Skip()

    def _on_activate(self, event: wx.ActivateEvent) -> None:
        # Catches a missed midnight (e.g. the PC was asleep) as soon as the user comes back.
        if event.GetActive() and _today() != self._today:
            wx.CallAfter(self.refresh)
        event.Skip()

    def _on_midnight(self, _event: wx.TimerEvent) -> None:
        self.refresh()
        self._arm_midnight_timer()
        self._reminder_timer.Start(_REMINDER_CHECK_MS)

    # ---------------------------------------------------------- show and close

    def show_window(self) -> None:
        self.refresh()
        self.Show()
        self.Iconize(False)
        self.Raise()
        self._list.SetFocus()

    def show_bill(self, series_id: int | None) -> None:
        """Bring the window up with that bill selected (from a clicked reminder)."""
        self.show_window()
        for i, row in enumerate(self._list.rows):
            if row.series.id == series_id:
                self._list.select(i)
                break

    def quit(self) -> None:
        self._shut_down()
        self.Destroy()

    def _shut_down(self) -> None:
        """Stop everything that would fire, or keep the app alive, after this window."""
        self._midnight_timer.Stop()
        self._reminder_timer.Stop()
        self._notifier.close()
        if self._tray is not None:
            self._tray.Destroy()
            self._tray = None

    def _on_close(self, event: wx.CloseEvent) -> None:
        if self._tray is not None and event.CanVeto():
            self.Hide()  # keep running in the tray
            event.Veto()
        else:
            self._shut_down()
            event.Skip()  # let the window (and, being the last one, the app) close
