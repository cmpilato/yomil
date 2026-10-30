"""Keeping her data safe while YOMIL runs, and recovering it if it's damaged at startup.

* :class:`SnapshotKeeper` refreshes the safety snapshot (``storage.snapshot``) within a
  couple of seconds of any change. It watches SQLite's change counter rather than
  hooking every write, so nothing else in the app has to remember to call it.
* :func:`check_and_recover` runs ``PRAGMA quick_check`` before the database is opened
  for use and, if it fails, offers to put the snapshot back.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import wx

from yomil.core.formatting import format_date_time
from yomil.storage.snapshot import is_intact, restore_snapshot, snapshot_path, write_snapshot

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

log = logging.getLogger(__name__)

CHECK_INTERVAL_MS = 2000


class SnapshotKeeper(wx.Timer):
    """Writes a snapshot at the first check, then whenever the database has changed."""

    def __init__(self, conn: sqlite3.Connection, db_path: Path) -> None:
        super().__init__()
        self._conn = conn
        self._dest = snapshot_path(db_path)
        self._saved_at_changes: int | None = None
        self._failing = False

    def start(self) -> None:
        self.Start(CHECK_INTERVAL_MS)

    def Notify(self) -> None:  # noqa: N802  (wx naming)
        self.flush()

    def flush(self) -> None:
        """Snapshot now if anything changed since the last one (also called at exit)."""
        changes = self._conn.total_changes
        if changes == self._saved_at_changes or self._conn.in_transaction:
            return
        try:
            write_snapshot(self._conn, self._dest)
        except Exception:
            # E.g. a backup program has the snapshot open. Try again next time; log
            # only the first failure in a row, so a long outage doesn't flood the log.
            if not self._failing:
                log.exception("Could not write the safety snapshot to %s", self._dest)
            self._failing = True
            return
        if self._failing:
            log.info("Safety snapshot written again")
        self._failing = False
        self._saved_at_changes = changes


def check_and_recover(db_path: Path) -> bool:
    """Check the database before use. Returns False if YOMIL should quit.

    A damaged database is replaced by the snapshot only if she agrees and the snapshot
    itself is intact; the damaged file is always kept.
    """
    if not db_path.exists() or is_intact(db_path):
        return True
    log.error("The database %s failed its integrity check", db_path)
    snapshot = snapshot_path(db_path)
    if not (snapshot.exists() and is_intact(snapshot)):
        wx.MessageBox(
            "YOMIL's data file is damaged, and there is no usable safety copy.\n\n"
            "Please don't use YOMIL until someone can look at it.\n\n"
            f"Data file: {db_path}",
            "YOMIL",
            wx.OK | wx.ICON_ERROR,
        )
        return False

    taken = datetime.fromtimestamp(snapshot.stat().st_mtime)  # noqa: DTZ006  (local time)
    dlg = wx.MessageDialog(
        None,
        "YOMIL's data file is damaged.\n\n"
        f"A safety copy from {format_date_time(taken)} can be put back. Anything "
        "changed after that time will need to be entered again.\n\n"
        "The damaged file will be kept, in case someone needs to look at it.",
        "YOMIL",
        wx.YES_NO | wx.YES_DEFAULT | wx.ICON_WARNING,
    )
    dlg.SetYesNoLabels("&Restore Safety Copy", "&Quit")
    restore = dlg.ShowModal() == wx.ID_YES
    dlg.Destroy()
    if not restore:
        return False
    try:
        damaged = restore_snapshot(db_path, datetime.now())  # noqa: DTZ005  (file name)
    except OSError:
        log.exception("Could not restore the snapshot")
        wx.MessageBox(
            f"YOMIL couldn't put the safety copy back.\n\nData file: {db_path}\n"
            f"Safety copy: {snapshot}",
            "YOMIL",
            wx.OK | wx.ICON_ERROR,
        )
        return False
    log.info("Damaged database kept as %s", damaged)
    wx.MessageBox("The safety copy has been put back.", "YOMIL", wx.OK | wx.ICON_INFORMATION)
    return True
