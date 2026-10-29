"""The main window's bill list: a virtual report-style ``wx.ListCtrl``.

Virtual means the control holds no data of its own; it calls ``OnGetItemText`` and
``OnGetItemAttr`` for the rows it is drawing, and we keep the rows in one Python list.
All wording comes from ``core.formatting``; this module only adds styling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from yomil.core.formatting import format_date, format_expected_amount, status_text
from yomil.core.urgency import Urgency

if TYPE_CHECKING:
    from datetime import date

    from yomil.core.formatting import MoneyFormat
    from yomil.core.main_list import BillRow

COLUMNS = ("Due", "Bill", "Amount", "Status", "Note")
_AMOUNT_COL = COLUMNS.index("Amount")
_MIN_NOTE_WIDTH_CHARS = 20

# (text, background) per urgency. Overdue is a saturated red with white bold text, due
# soon a pale amber: they differ strongly in lightness, so they stay distinct with any
# kind of color blindness. Status text says the same thing without color.
_LIGHT = {
    Urgency.OVERDUE: ("#FFFFFF", "#B3261E"),
    Urgency.DUE_SOON: ("#000000", "#FFE8A3"),
}
_DARK = {
    Urgency.OVERDUE: ("#FFFFFF", "#B3261E"),
    Urgency.DUE_SOON: ("#FFF1C1", "#5C4500"),
}


class BillListCtrl(wx.ListCtrl):
    def __init__(self, parent: wx.Window, money_fmt: MoneyFormat) -> None:
        super().__init__(
            parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL | wx.LC_HRULES
        )
        self._money_fmt = money_fmt
        self._rows: list[BillRow] = []
        self._cells: list[tuple[str, ...]] = []
        self._attrs: dict[Urgency, wx.ItemAttr] = {}
        for i, title in enumerate(COLUMNS):
            self.InsertColumn(i, title, wx.LIST_FORMAT_RIGHT if i == _AMOUNT_COL else 0)
        self._build_attrs()
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self._on_sys_colour_changed)

    # ------------------------------------------------------------------ public

    def set_rows(self, rows: list[BillRow], today: date) -> None:
        self._rows = rows
        self._cells = [
            (
                format_date(r.occurrence.due_date),
                r.series.payee,
                format_expected_amount(r, self._money_fmt),
                status_text(r, today),
                r.occurrence.note or "",
            )
            for r in rows
        ]
        self.SetItemCount(len(rows))
        self._fit_columns()
        self.Refresh()

    def apply_font(self, points: int | None) -> None:
        """Use ``points`` (or the system default size) for the rows and headers."""
        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        if points is not None:
            font.SetPointSize(points)
        if font == self.GetFont():
            return
        self.SetFont(font)
        self._build_attrs()
        self._fit_columns()
        self.Refresh()

    def extra_width_needed(self) -> int:
        """How much wider the control must be to show every column without scrolling."""
        columns = sum(self.GetColumnWidth(c) for c in range(self.GetColumnCount()))
        scrollbar = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X, self)
        return max(0, columns + scrollbar - self.GetClientSize().width)

    @property
    def rows(self) -> list[BillRow]:
        return self._rows

    def selected_index(self) -> int:
        """The selected row's index, or -1."""
        return int(self.GetFirstSelected())

    def selected_row(self) -> BillRow | None:
        i = self.selected_index()
        return self._rows[i] if 0 <= i < len(self._rows) else None

    def select(self, index: int) -> None:
        """Select and focus row ``index`` (clamped), so the keyboard carries on from there."""
        if not self._rows:
            return
        index = max(0, min(index, len(self._rows) - 1))
        self.Select(index)
        self.Focus(index)  # also scrolls it into view

    # ------------------------------------------------------- virtual callbacks

    def OnGetItemText(self, item: int, column: int) -> str:  # noqa: N802  (wx naming)
        return self._cells[item][column]

    def OnGetItemAttr(self, item: int) -> wx.ItemAttr | None:  # noqa: N802  (wx naming)
        return self._attrs.get(self._rows[item].urgency)

    # ---------------------------------------------------------------- private

    def _build_attrs(self) -> None:
        dark = wx.SystemSettings.GetAppearance().IsDark()
        font = self.GetFont()
        bold = font.Bold()
        self._attrs = {
            urgency: wx.ItemAttr(
                wx.Colour(fg), wx.Colour(bg), bold if urgency is Urgency.OVERDUE else font
            )
            for urgency, (fg, bg) in (_DARK if dark else _LIGHT).items()
        }

    def _fit_columns(self) -> None:
        """Size each column to its widest cell, measured in the font actually used."""
        dc = wx.ClientDC(self)
        pad = self.FromDIP(16)
        fonts = {u: a.GetFont() for u, a in self._attrs.items()}
        widths = []
        for col, title in enumerate(COLUMNS):
            dc.SetFont(self.GetFont())
            width = dc.GetTextExtent(title).width
            for row, cells in zip(self._rows, self._cells, strict=True):
                dc.SetFont(fonts.get(row.urgency, self.GetFont()))
                width = max(width, dc.GetTextExtent(cells[col]).width)
            widths.append(width + pad)
        widths[-1] = max(widths[-1], dc.GetCharWidth() * _MIN_NOTE_WIDTH_CHARS)
        for col, width in enumerate(widths):
            self.SetColumnWidth(col, width)

    def _on_sys_colour_changed(self, event: wx.SysColourChangedEvent) -> None:
        self._build_attrs()
        self.Refresh()
        event.Skip()
