"""Preferences: the text size and the "due soon" window, with a live preview.

The preview is a real bill list (with made-up bills from ``core.preferences``) and a
sample field, so what the user sees is exactly what they'll get. Nothing changes until Save;
then the main window applies it right away and every dialog opened after uses it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from yomil.app.bill_list import BillListCtrl
from yomil.app.fields import grow_to_fit
from yomil.app.fonts import default_font_size, inherit_font, set_font_everywhere, ui_font
from yomil.core.errors import YomilError
from yomil.core.preferences import sample_rows, threshold_explanation
from yomil.services import settings

if TYPE_CHECKING:
    import sqlite3
    from datetime import date

    from yomil.core.formatting import MoneyFormat

_PREVIEW_LINES = 5  # header plus the sample rows, with a little room


class PreferencesDialog(wx.Dialog):
    """Modal. Returns ``wx.ID_OK`` from ``ShowModal()`` if it saved."""

    def __init__(
        self,
        parent: wx.Window,
        conn: sqlite3.Connection,
        *,
        money_fmt: MoneyFormat,
        today: date,
    ) -> None:
        super().__init__(
            parent, title="Preferences", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        inherit_font(self, parent)  # before creating any controls
        self._conn = conn
        self._today = today
        self._default_size = default_font_size()
        self._initial = (
            settings.font_size(conn) or self._default_size,
            settings.upcoming_threshold_days(conn),
        )
        font_points, threshold = self._initial
        gap = self.FromDIP(8)

        # Text size
        text_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Text size")
        box = text_box.GetStaticBox()
        self._size = wx.SpinCtrl(
            box,
            min=settings.MIN_FONT_SIZE,
            max=settings.MAX_FONT_SIZE,
            initial=font_points,
            style=wx.SP_ARROW_KEYS | wx.ALIGN_RIGHT,
        )
        reset = wx.Button(box, label=f"Use &Windows Size ({self._default_size})")
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(
            wx.StaticText(box, label="&Text size:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, gap
        )
        row.Add(self._size, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, gap)
        row.Add(wx.StaticText(box, label="points"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2 * gap)
        row.Add(reset, 0, wx.ALIGN_CENTER_VERTICAL)
        text_box.Add(row, 0, wx.ALL, gap)
        text_box.Add(
            wx.StaticText(box, label="Used in all of YOMIL's windows."),
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM,
            gap,
        )

        # Due soon
        soon_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Due soon")
        box = soon_box.GetStaticBox()
        self._threshold = wx.SpinCtrl(
            box,
            min=settings.MIN_THRESHOLD_DAYS,
            max=settings.MAX_THRESHOLD_DAYS,
            initial=threshold,
            style=wx.SP_ARROW_KEYS | wx.ALIGN_RIGHT,
        )
        self._explanation = wx.StaticText(box)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(box, label="&Due soon:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, gap)
        row.Add(self._threshold, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, gap)
        row.Add(wx.StaticText(box, label="days ahead"), 0, wx.ALIGN_CENTER_VERTICAL)
        soon_box.Add(row, 0, wx.ALL, gap)
        soon_box.Add(self._explanation, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, gap)

        # Preview
        preview_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Preview")
        box = preview_box.GetStaticBox()
        self._preview = wx.Panel(box)
        self._preview_list = BillListCtrl(self._preview, money_fmt)
        sample_field = wx.TextCtrl(self._preview, value="This is how typing will look.")
        preview_sizer = wx.BoxSizer(wx.VERTICAL)
        preview_sizer.Add(self._preview_list, 1, wx.EXPAND | wx.BOTTOM, gap)
        preview_sizer.Add(sample_field, 0, wx.EXPAND)
        self._preview.SetSizer(preview_sizer)
        preview_box.Add(self._preview, 1, wx.EXPAND | wx.ALL, gap)

        save = wx.Button(self, wx.ID_SAVE, label="&Save")
        cancel = wx.Button(self, wx.ID_CANCEL, label="&Cancel")  # also Escape and the X
        save.SetDefault()
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(save)
        buttons.AddStretchSpacer()
        buttons.Add(cancel)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(text_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 2 * gap)
        sizer.Add(soon_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 2 * gap)
        sizer.Add(preview_box, 1, wx.EXPAND | wx.ALL, 2 * gap)
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 2 * gap)
        self.SetSizer(sizer)

        for spin in (self._size, self._threshold):
            spin.Bind(wx.EVT_SPINCTRL, lambda _evt: self._update_preview())
            spin.Bind(wx.EVT_TEXT, lambda _evt: self._update_preview())
        reset.Bind(wx.EVT_BUTTON, self._on_reset)
        save.Bind(wx.EVT_BUTTON, self._on_save)
        cancel.Bind(wx.EVT_BUTTON, self._on_cancel)

        self._shown: tuple[int, int] | None = None
        self._update_preview()
        self.Fit()
        self.CentreOnParent()
        self._size.SetFocus()

    def _values(self) -> tuple[int, int]:
        return self._size.GetValue(), self._threshold.GetValue()

    def _update_preview(self) -> None:
        values = self._values()
        if values == self._shown:
            return
        points, threshold = values
        font = ui_font(points)
        set_font_everywhere(self._preview, font)
        self._preview_list.apply_font(font)
        self._preview_list.set_rows(sample_rows(self._today, threshold), self._today)
        self._explanation.SetLabel(threshold_explanation(threshold))

        # Room for every column and row of the sample, without scrolling.
        columns = sum(
            self._preview_list.GetColumnWidth(c) for c in range(self._preview_list.GetColumnCount())
        )
        line = self._preview_list.GetCharHeight() + self.FromDIP(10)
        widest = wx.Display(self).GetClientArea().width * 3 // 4  # past that, it scrolls
        self._preview_list.SetMinSize(
            wx.Size(min(columns + self.FromDIP(8), widest), line * _PREVIEW_LINES)
        )
        self._preview.Layout()
        self._shown = values
        grow_to_fit(self)

    def _on_reset(self, _event: wx.CommandEvent) -> None:
        self._size.SetValue(self._default_size)
        self._update_preview()
        self._size.SetFocus()

    def _on_save(self, _event: wx.CommandEvent) -> None:
        if self._save():
            self.EndModal(wx.ID_OK)

    def _save(self) -> bool:
        points, threshold = self._values()
        try:
            settings.save_preferences(
                self._conn,
                # The chosen size, or None to follow Windows if that's the size picked.
                font_size=None if points == self._default_size else points,
                upcoming_threshold_days=threshold,
            )
        except YomilError as exc:
            wx.MessageBox(str(exc), "YOMIL", wx.OK | wx.ICON_WARNING, self)
            return False
        return True

    def _on_cancel(self, _event: wx.CommandEvent) -> None:
        if self._values() != self._initial:
            dlg = wx.MessageDialog(
                self,
                "Save your changes to the preferences?",
                "Unsaved Changes",
                wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
            )
            dlg.SetYesNoCancelLabels("&Save", "&Don't Save", "&Keep Editing")
            answer = dlg.ShowModal()
            dlg.Destroy()
            if answer == wx.ID_CANCEL:
                return
            if answer == wx.ID_YES:
                if self._save():
                    self.EndModal(wx.ID_OK)
                return
        self.EndModal(wx.ID_CANCEL)
