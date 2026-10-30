"""Showing reminder notifications (``wx.adv.NotificationMessage``).

On Windows, an installed YOMIL uses native toasts. Those need a Start Menu shortcut with
an AppUserModelID; wx checks for it, and creates or fixes it if needed. A dev run (not
frozen) uses the tray icon's balloon instead, which Windows 10 and 11 also draw as a
toast, so no shortcut to ``python.exe`` ends up in the Start Menu. Elsewhere, wx uses
the desktop's own notifications (libnotify on Linux).
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import wx
import wx.adv

if TYPE_CHECKING:
    from collections.abc import Callable

    from yomil.core.reminders import Notice

log = logging.getLogger(__name__)

# wxPython has the event types but no binders for them.
EVT_NOTIFICATION_MESSAGE_CLICK: wx.PyEventBinder[wx.CommandEvent] = wx.PyEventBinder(
    wx.adv.wxEVT_NOTIFICATION_MESSAGE_CLICK
)
EVT_NOTIFICATION_MESSAGE_DISMISSED: wx.PyEventBinder[wx.CommandEvent] = wx.PyEventBinder(
    wx.adv.wxEVT_NOTIFICATION_MESSAGE_DISMISSED
)

_KEEP = 20  # notifications kept alive so their click events still arrive


class Notifier:
    def __init__(self, parent: wx.Window, tray: wx.adv.TaskBarIcon | None) -> None:
        self._parent = parent
        self._live: list[wx.adv.NotificationMessage] = []
        if sys.platform != "win32":
            return
        toasts = False
        if getattr(sys, "frozen", False):
            try:
                toasts = bool(wx.adv.NotificationMessage.MSWUseToasts())
            except Exception:
                log.exception("Could not enable toast notifications")
        if not toasts and tray is not None:
            wx.adv.NotificationMessage.UseTaskBarIcon(tray)

    def show(self, notice: Notice, on_click: Callable[[int | None], None]) -> bool:
        """Show ``notice``; clicking it calls ``on_click(notice.series_id)``."""
        msg = wx.adv.NotificationMessage(notice.title, notice.body, parent=self._parent)
        msg.Bind(EVT_NOTIFICATION_MESSAGE_CLICK, lambda _evt: on_click(notice.series_id))
        msg.Bind(EVT_NOTIFICATION_MESSAGE_DISMISSED, lambda _evt: self._forget(msg))
        if not msg.Show(wx.adv.NotificationMessage.Timeout_Auto):
            log.warning("Could not show the notification %r", notice.title)
            return False
        self._live = [*self._live[-(_KEEP - 1) :], msg]
        return True

    def _forget(self, msg: wx.adv.NotificationMessage) -> None:
        if msg in self._live:
            self._live.remove(msg)
