"""Logging that works for a console-less (pythonw / windowed) process.

With no console, ``print()`` output and uncaught tracebacks vanish, so everything
goes to a rotating log file, and uncaught exceptions are routed into it.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging(log_file: Path, *, level: int = logging.INFO) -> None:
    """Install a rotating file handler on the root logger and a crash hook."""
    handler = RotatingFileHandler(log_file, maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    def _log_uncaught(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logging.getLogger("yomil").critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = _log_uncaught
