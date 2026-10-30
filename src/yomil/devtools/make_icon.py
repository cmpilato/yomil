"""Draw YOMIL's icon and write it as a multi-size ``.ico`` (``make icon``; needs wx).

A calendar page with a check mark on a blue tile. Each size is drawn separately (not
scaled down from the largest), so the small ones stay crisp. The ``.ico`` holds PNG
images, which Windows has accepted since Vista.
"""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path
from typing import Any

import wx

SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "app" / "icons" / "yomil.ico"

_BLUE = wx.Colour(30, 100, 190)
_RED = wx.Colour(179, 38, 30)
_GREEN = wx.Colour(30, 140, 70)


def draw(size: int) -> bytes:
    """One square PNG image of the icon."""
    image = wx.Image(size, size)
    image.InitAlpha()
    image.SetAlpha(bytes(size * size))  # fully transparent to start
    bmp = wx.Bitmap(image)
    dc = wx.MemoryDC(bmp)
    gc = wx.GraphicsContext.Create(dc)
    s = size / 32  # the design is laid out on a 32-unit grid

    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(_BLUE))
    gc.DrawRoundedRectangle(0, 0, size, size, 6 * s)
    gc.SetBrush(wx.Brush(wx.WHITE))
    gc.DrawRoundedRectangle(6 * s, 6 * s, 20 * s, 21 * s, 2 * s)  # the page
    gc.SetBrush(wx.Brush(_RED))
    gc.DrawRectangle(6 * s, 6 * s, 20 * s, 5 * s)  # the calendar's header band
    check = gc.CreatePath()
    check.MoveToPoint(10.5 * s, 18.5 * s)
    check.AddLineToPoint(14.5 * s, 22.5 * s)
    check.AddLineToPoint(21.5 * s, 14 * s)
    pen = wx.GraphicsPenInfo(_GREEN).Width(max(1.5, 3 * s)).Cap(wx.CAP_ROUND).Join(wx.JOIN_ROUND)
    gc.SetPen(gc.CreatePen(pen))
    gc.StrokePath(check)
    del gc
    dc.SelectObject(wx.NullBitmap)

    stream = io.BytesIO()
    # wxPython takes any file-like object here; its stubs only list file names.
    png: Any = bmp.ConvertToImage()
    png.SaveFile(stream, wx.BITMAP_TYPE_PNG)
    return stream.getvalue()


def write_ico(images: dict[int, bytes], path: Path) -> None:
    """Pack PNG images into an ``.ico`` file (header, directory, then the images)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    directory, data = b"", b""
    for size, png in sorted(images.items()):
        side = size % 256  # 0 means 256
        directory += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        data += png
        offset += len(png)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + directory + data)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    out = Path(args[0]) if args else DEFAULT_OUT
    app = wx.App()  # noqa: F841  (wx needs an app object to draw)
    write_ico({size: draw(size) for size in SIZES}, out)
    sys.stderr.write(f"Wrote {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
