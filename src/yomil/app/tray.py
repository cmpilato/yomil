"""Taskbar (notification area) icon."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import wx
import wx.adv

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from yomil.app.frame import MainFrame

_ID_OPEN = wx.NewIdRef()
_ID_QUIT = wx.NewIdRef()


def tray_available() -> bool:
    """Whether a notification-area icon can be shown.

    Windows always has one. Elsewhere (notably stock GNOME) it may not, and hiding the
    window with no tray icon would leave an unreachable background process.
    """
    if sys.platform == "win32":
        return True
    try:
        return bool(wx.adv.TaskBarIcon.IsAvailable())
    except Exception:
        log.exception("Could not determine tray availability; assuming none")
        return False


def make_icon() -> wx.Icon:
    """Draw a placeholder icon in code so no binary asset is needed yet."""
    bmp = wx.Bitmap(32, 32)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(30, 100, 190)))
    dc.Clear()
    dc.SetBrush(wx.Brush(wx.WHITE))
    dc.SetPen(wx.TRANSPARENT_PEN)
    dc.DrawRectangle(8, 6, 16, 20)
    dc.SelectObject(wx.NullBitmap)
    icon = wx.Icon()
    icon.CopyFromBitmap(bmp)
    return icon


class TrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame: MainFrame) -> None:
        super().__init__()
        self._frame = frame
        self.SetIcon(make_icon(), "YOMIL")
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, lambda _evt: self._frame.show_window())
        self.Bind(wx.EVT_MENU, lambda _evt: self._frame.show_window(), id=_ID_OPEN)
        self.Bind(wx.EVT_MENU, lambda _evt: self._frame.quit(), id=_ID_QUIT)

    def CreatePopupMenu(self) -> wx.Menu:  # noqa: N802  (wx naming)
        menu = wx.Menu()
        menu.Append(_ID_OPEN, "Open YOMIL")
        menu.AppendSeparator()
        menu.Append(_ID_QUIT, "Quit")
        return menu
