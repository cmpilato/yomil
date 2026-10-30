"""Conversions between ``datetime.date`` and ``wx.DateTime`` (whose months count from 0)."""

from __future__ import annotations

from datetime import date

import wx


def to_wx(d: date) -> wx.DateTime:
    return wx.DateTime.FromDMY(d.day, d.month - 1, d.year)


def from_wx(dt: wx.DateTime) -> date:
    return date(dt.GetYear(), dt.GetMonth() + 1, dt.GetDay())
