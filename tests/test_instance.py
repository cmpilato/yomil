from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING

import pytest

from yomil import instance

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def addr(tmp_path: Path) -> str:
    if sys.platform == "win32":
        return instance.address(f"test-{tmp_path.name}")
    return str(tmp_path / "yomil.sock")


def test_a_second_launch_asks_the_first_to_show(addr: str) -> None:
    shown = threading.Event()
    requests = instance.ShowRequests(addr, shown.set)
    try:
        assert instance.ask_running_copy_to_show(addr)
        assert shown.wait(timeout=5)
        shown.clear()
        assert instance.ask_running_copy_to_show(addr)  # and again, later
        assert shown.wait(timeout=5)
    finally:
        requests.close()


def test_nobody_listening(addr: str) -> None:
    assert not instance.ask_running_copy_to_show(addr)


@pytest.mark.skipif(sys.platform == "win32", reason="named pipes leave no file behind")
def test_a_crashed_copys_socket_file_is_replaced(addr: str, tmp_path: Path) -> None:
    (tmp_path / "yomil.sock").write_text("left over")
    shown = threading.Event()
    requests = instance.ShowRequests(addr, shown.set)
    try:
        assert instance.ask_running_copy_to_show(addr)
        assert shown.wait(timeout=5)
    finally:
        requests.close()
