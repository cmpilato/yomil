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


def make_icon(badge: int = 0) -> wx.Icon:
    """Draw a placeholder icon in code so no binary asset is needed yet.

    ``badge``, if non-zero, is drawn as a number in a red circle (the overdue count): a
    number, not just a color, and repeated in the tooltip.
    """
    bmp = wx.Bitmap(32, 32)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(30, 100, 190)))
    dc.Clear()
    dc.SetBrush(wx.Brush(wx.WHITE))
    dc.SetPen(wx.TRANSPARENT_PEN)
    dc.DrawRectangle(8, 6, 16, 20)
    if badge:
        dc.SetBrush(wx.Brush(wx.Colour("#B3261E")))
        dc.SetPen(wx.Pen(wx.WHITE, 2))
        dc.DrawCircle(21, 21, 10)
        text = str(badge) if badge < 10 else "9+"
        dc.SetFont(wx.Font(wx.FontInfo(12 if badge < 10 else 9).Bold()))
        dc.SetTextForeground(wx.WHITE)
        extent = dc.GetTextExtent(text)
        dc.DrawText(text, 21 - extent.width // 2, 21 - extent.height // 2)
    dc.SelectObject(wx.NullBitmap)
    icon = wx.Icon()
    icon.CopyFromBitmap(bmp)
    return icon


class TrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame: MainFrame) -> None:
        super().__init__()
        self._frame = frame
        self._state: tuple[str, int] | None = None
        self.SetIcon(make_icon(), "YOMIL")
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, lambda _evt: self._frame.show_window())
        self.Bind(wx.EVT_MENU, lambda _evt: self._frame.show_window(), id=_ID_OPEN)
        self.Bind(wx.EVT_MENU, lambda _evt: self._frame.quit(), id=_ID_QUIT)

    def update(self, summary: str, overdue: int) -> None:
        """Show the main list's summary as the tooltip, and the overdue count as a badge."""
        state = (summary, overdue)
        if state != self._state:
            self._state = state
            self.SetIcon(make_icon(overdue), f"YOMIL: {summary}")

    def CreatePopupMenu(self) -> wx.Menu:  # noqa: N802  (wx naming)
        menu = wx.Menu()
        menu.Append(_ID_OPEN, "Open YOMIL")
        menu.AppendSeparator()
        menu.Append(_ID_QUIT, "Quit")
        return menu
