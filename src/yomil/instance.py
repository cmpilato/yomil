"""Bringing up the running YOMIL when it's launched again.

YOMIL usually runs hidden in the tray, so launching it again (Start Menu, desktop icon,
the installer's "Launch YOMIL") must show the running copy's window rather than quietly
do nothing. The running copy listens on a per-user local channel (a named pipe on
Windows, a Unix socket elsewhere); a second launch connects, asks it to show itself, and
exits. Only one copy runs at a time; that's decided separately (``wx.SingleInstanceChecker``).
"""

from __future__ import annotations

import logging
import sys
import tempfile
import threading
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)

_AUTHKEY = b"yomil-show"  # not a secret: it only keeps stray connections out
SHOW = "show"


def address(user: str) -> str:
    """The channel for ``user`` (one YOMIL per Windows account)."""
    if sys.platform == "win32":
        return rf"\\.\pipe\yomil-{user}"
    return str(Path(tempfile.gettempdir()) / f"yomil-{user}.sock")


def ask_running_copy_to_show(addr: str) -> bool:
    """Ask the running copy to bring its window up. False if it couldn't be reached."""
    try:
        with Client(addr, authkey=_AUTHKEY) as conn:
            conn.send(SHOW)
    except (OSError, EOFError) as exc:
        log.warning("Could not reach the running YOMIL at %s: %s", addr, exc)
        return False
    return True


class ShowRequests:
    """Listens for :func:`ask_running_copy_to_show` and calls ``on_show`` for each.

    ``on_show`` runs on a background thread; a GUI should hand it to its own thread
    (``wx.CallAfter``).
    """

    def __init__(self, addr: str, on_show: Callable[[], None]) -> None:
        if sys.platform != "win32":
            # Only one copy gets this far, so a socket file left here belongs to a copy
            # that crashed.
            Path(addr).unlink(missing_ok=True)
        self._listener = Listener(addr, authkey=_AUTHKEY)
        self._on_show = on_show
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="show-requests", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                with self._listener.accept() as conn:
                    message = conn.recv()
            except Exception:
                if self._closed.is_set():
                    return
                log.exception("A request to show YOMIL failed")
                continue
            if message == SHOW:
                self._on_show()

    def close(self) -> None:
        self._closed.set()
        try:
            self._listener.close()
        except OSError:
            log.exception("Could not close the show-request listener")
