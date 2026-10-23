from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from yomil.logging_setup import configure_logging

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_uncaught_exceptions_are_logged_to_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)  # restored after the test
    root = logging.getLogger()
    before = list(root.handlers)
    log_file = tmp_path / "t.log"
    try:
        configure_logging(log_file)
        try:
            raise ValueError("boom")
        except ValueError:
            sys.excepthook(*sys.exc_info())  # type: ignore[arg-type]
        for handler in root.handlers:
            handler.flush()
        text = log_file.read_text(encoding="utf-8")
        assert "Uncaught exception" in text
        assert "boom" in text
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
                handler.close()
