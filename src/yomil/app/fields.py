"""Helpers shared by the editing dialogs: messages next to fields, and growing to fit them."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

if TYPE_CHECKING:
    from yomil.core.forms import FieldMessage

_ERROR_COLOUR_LIGHT = "#B3261E"
_ERROR_COLOUR_DARK = "#FF8A80"


def show_message(label: wx.StaticText, message: FieldMessage | None) -> None:
    """Errors get a ⚠ as well as a colour, so they never rely on colour alone."""
    if message is None:
        label.SetLabel("")
    elif message.is_error:
        dark = wx.SystemSettings.GetAppearance().IsDark()
        label.SetLabel(f"⚠ {message.text}")
        label.SetForegroundColour(wx.Colour(_ERROR_COLOUR_DARK if dark else _ERROR_COLOUR_LIGHT))
    else:
        label.SetLabel(message.text)
        label.SetForegroundColour(wx.NullColour)


def grow_to_fit(window: wx.TopLevelWindow) -> None:
    """Make room for longer text (never shrink, so the layout doesn't jump; never past
    the screen, so very large text scrolls rather than vanishing off the edge)."""
    window.Layout()
    needed = window.GetSizer().ComputeFittingWindowSize(window)
    size = window.GetSize()
    if needed.width > size.width or needed.height > size.height:
        area = wx.Display(window).GetClientArea()
        window.SetSize(
            min(max(needed.width, size.width), area.width),
            min(max(needed.height, size.height), area.height),
        )
        window.Layout()
