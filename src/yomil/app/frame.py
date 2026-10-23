"""Main window.

With a tray icon, closing the window hides it and the tray menu's Quit really exits.
Without one (``--no-tray`` or no tray available), closing the window quits the app.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from yomil.app.tray import TrayIcon, make_icon

if TYPE_CHECKING:
    import sqlite3


class MainFrame(wx.Frame):
    def __init__(self, conn: sqlite3.Connection, *, use_tray: bool = True) -> None:
        super().__init__(None, title="YOMIL", size=(720, 480))
        self._conn = conn
        self.SetIcon(make_icon())
        self._tray: TrayIcon | None = TrayIcon(self) if use_tray else None
        self.Bind(wx.EVT_CLOSE, self._on_close)
        wx.StaticText(self, label="YOMIL is running. UI coming soon.", pos=(20, 20))

    def show_window(self) -> None:
        self.Show()
        self.Iconize(False)
        self.Raise()

    def quit(self) -> None:
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
            self._destroy_tray()
            event.Skip()  # let the window (and, being the last one, the app) close
