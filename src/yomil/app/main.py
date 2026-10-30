"""Application entry point (``yomil`` gui-script and ``python -m yomil``)."""

from __future__ import annotations

import argparse
import locale
import logging
import sys
from pathlib import Path

from yomil import __version__, instance
from yomil.core.formatting import USD, MoneyFormat, money_format_from_localeconv
from yomil.logging_setup import configure_logging
from yomil.paths import default_db_path, log_dir
from yomil.storage import db

log = logging.getLogger("yomil")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="yomil")
    parser.add_argument(
        "--minimized", action="store_true", help="start hidden in the tray (used at login)"
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="no tray icon; closing the window quits (default when no tray is available)",
    )
    parser.add_argument("--db", help="path to the SQLite database (default: per-user data dir)")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=argparse.SUPPRESS,  # for the packaging build: check the bundle, then exit
    )
    return parser.parse_args(argv)


def _locale_money_format() -> MoneyFormat:
    """Snapshot the user's currency format, then put the process locale back.

    Done before ``wx.App`` exists: wx manages the C runtime locale itself (on Windows it
    asserts if Python changes it underneath), so we only borrow it briefly here.
    """
    try:
        previous = locale.setlocale(locale.LC_MONETARY)
        locale.setlocale(locale.LC_MONETARY, "")
        try:
            return money_format_from_localeconv(locale.localeconv())
        finally:
            locale.setlocale(locale.LC_MONETARY, previous)
    except locale.Error:
        log.warning("Could not read the locale's currency format; using USD")
        return USD


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging(log_dir() / "yomil.log")
    log.info("YOMIL %s starting", __version__)

    if args.self_test:
        return _self_test()

    money_fmt = _locale_money_format()

    # Import wx lazily so `--help` and the headless core work without it installed.
    import wx

    app = wx.App()

    checker = wx.SingleInstanceChecker(f"yomil-{wx.GetUserId()}")
    show_address = instance.address(wx.GetUserId())
    if checker.IsAnotherRunning():
        log.info("Another instance is already running; asking it to show its window")
        instance.ask_running_copy_to_show(show_address)
        return 0

    from yomil.app.frame import MainFrame
    from yomil.app.safety import SnapshotKeeper, check_and_recover
    from yomil.app.tray import tray_available

    db_path = Path(args.db) if args.db else default_db_path()
    if not check_and_recover(db_path):
        return 1
    conn = db.connect(db_path)
    db.migrate(conn)
    snapshots = SnapshotKeeper(conn, db_path)
    snapshots.start()

    use_tray = not args.no_tray and tray_available()
    if not use_tray:
        log.info("Running without a tray icon")
    frame = MainFrame(conn, money_fmt=money_fmt, use_tray=use_tray, db_path=db_path)
    try:
        show_requests: instance.ShowRequests | None = instance.ShowRequests(
            show_address, lambda: wx.CallAfter(frame.show_window)
        )
    except OSError:
        log.exception("Could not listen for requests to show the window")
        show_requests = None

    def on_end_session(event: wx.CloseEvent) -> None:
        # Signing out, shutting down, or the installer closing YOMIL to upgrade it: the
        # process may not live past this, so save the snapshot now.
        snapshots.flush()
        event.Skip()  # wx then closes the windows

    app.Bind(wx.EVT_END_SESSION, on_end_session)
    # Without a tray there would be no way to reach a hidden window, so always show it.
    if not args.minimized or not use_tray:
        frame.show_window()
    app.MainLoop()
    if show_requests is not None:
        show_requests.close()
    snapshots.Stop()
    snapshots.flush()
    conn.close()
    return 0


def _self_test() -> int:
    """Check that a frozen build has everything it needs (no window, no user data)."""
    from importlib import resources

    conn = db.connect(":memory:")
    version = db.migrate(conn)
    conn.close()
    icon = resources.files("yomil.app") / "icons" / "yomil.ico"
    if not icon.is_file():
        log.error("Self-test: the icon is missing")
        return 1
    import wx  # noqa: F401  (it must at least import)

    log.info("Self-test passed (schema v%d)", version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
