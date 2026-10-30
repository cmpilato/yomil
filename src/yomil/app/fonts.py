"""Her text size, applied to every window YOMIL draws.

wx passes an explicitly set font down to child windows as they're *created*, but not to
top-level windows (dialogs) and not to children that already exist. So:

* each dialog calls :func:`inherit_font` first thing, before creating its controls;
* the main window, which outlives a change of setting, uses :func:`set_font_everywhere`.

Native menus, message boxes, and date-picker popups follow Windows' own text size.
"""

from __future__ import annotations

import wx


def ui_font(points: int | None) -> wx.Font:
    """The system UI font at ``points`` (``None``: its default size)."""
    font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    if points is not None:
        font.SetPointSize(points)
    return font


def default_font_size() -> int:
    return int(wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT).GetPointSize())


def inherit_font(dialog: wx.TopLevelWindow, parent: wx.Window) -> None:
    """Give a new dialog its parent's font (call before creating its controls)."""
    dialog.SetFont(parent.GetFont())


def set_font_everywhere(window: wx.Window, font: wx.Font) -> None:
    """Change the font of ``window`` and everything already inside it."""
    window.SetFont(font)
    for child in window.GetChildren():
        if not child.IsTopLevel():
            set_font_everywhere(child, font)


def scale_size_to_font(window: wx.TopLevelWindow) -> None:
    """Grow a window's starting size in step with a larger font (never past the screen)."""
    scale = window.GetFont().GetPointSize() / default_font_size()
    if scale <= 1:
        return
    area = wx.Display(window).GetClientArea()
    size = window.GetSize()
    window.SetSize(
        min(round(size.width * scale), area.width), min(round(size.height * scale), area.height)
    )
