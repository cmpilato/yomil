from __future__ import annotations

import pytest

from yomil import autostart


@pytest.mark.parametrize(
    ("executable", "frozen", "command"),
    [
        (
            r"C:\Program Files\YOMIL\yomil.exe",
            True,
            r'"C:\Program Files\YOMIL\yomil.exe" --minimized',
        ),
        (
            r"C:\src\yomil\.venv\Scripts\python.exe",
            False,
            r'"C:\src\yomil\.venv\Scripts\pythonw.exe" -m yomil --minimized',
        ),
        (
            r"C:\src\yomil\.venv\Scripts\pythonw.exe",
            False,
            r'"C:\src\yomil\.venv\Scripts\pythonw.exe" -m yomil --minimized',
        ),
    ],
)
def test_launch_command(executable: str, frozen: bool, command: str) -> None:
    assert autostart.launch_command(executable, frozen=frozen) == command


@pytest.mark.skipif(autostart.supported(), reason="the registry is real on Windows")
def test_does_nothing_off_windows() -> None:
    autostart.set_enabled(True)
    assert not autostart.is_enabled()
