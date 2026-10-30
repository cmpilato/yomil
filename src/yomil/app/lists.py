"""Helpers for the plain report ``wx.ListCtrl``s (Manage Bills, Payment History)."""

from __future__ import annotations

import wx


def apply_list_font(ctrl: wx.ListCtrl, points: int | None) -> None:
    """Use her preferred list font size (``None``: the system default)."""
    if points is not None:
        font = ctrl.GetFont()
        font.SetPointSize(points)
        ctrl.SetFont(font)


def fit_columns(ctrl: wx.ListCtrl) -> None:
    """Size each column to the wider of its header and its widest cell."""
    for col in range(ctrl.GetColumnCount()):
        ctrl.SetColumnWidth(col, wx.LIST_AUTOSIZE)
        cells_width = ctrl.GetColumnWidth(col)
        ctrl.SetColumnWidth(col, wx.LIST_AUTOSIZE_USEHEADER)
        if ctrl.GetColumnWidth(col) < cells_width:
            ctrl.SetColumnWidth(col, cells_width)
