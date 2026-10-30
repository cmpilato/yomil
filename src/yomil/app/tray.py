"""Taskbar (notification area) icon."""

from __future__ import annotations

import logging
import sys
from importlib import resources
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


def _icon_file() -> str:
    """The bundled ``.ico`` (drawn by ``yomil.devtools.make_icon``)."""
    return str(resources.files("yomil.app") / "icons" / "yomil.ico")


def app_icons() -> wx.IconBundle:
    """Every size of the app icon, so Windows can pick the right one for each place."""
    return wx.IconBundle(_icon_file())


def make_icon(badge: int = 0) -> wx.Icon:
    """The 32-pixel app icon, for the tray.

    ``badge``, if non-zero, is drawn as a number in a red circle (the overdue count): a
    number, not just a color, and repeated in the tooltip.
    """
    icon = wx.Icon(_icon_file(), wx.BITMAP_TYPE_ICO, 32, 32)
    if not badge:
        return icon
    bmp = wx.Bitmap(icon)
    dc = wx.MemoryDC(bmp)
    gc = wx.GraphicsContext.Create(dc)
    gc.SetBrush(wx.Brush(wx.Colour("#B3261E")))
    gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.WHITE).Width(2)))
    gc.DrawEllipse(11, 11, 20, 20)
    text = str(badge) if badge < 10 else "9+"
    gc.SetFont(wx.Font(wx.FontInfo(12 if badge < 10 else 9).Bold()), wx.WHITE)
    width, height = gc.GetTextExtent(text)
    gc.DrawText(text, 21 - width / 2, 21 - height / 2)
    del gc
    dc.SelectObject(wx.NullBitmap)
    badged = wx.Icon()
    badged.CopyFromBitmap(bmp)
    return badged


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
