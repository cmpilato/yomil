"""Starting YOMIL when the user signs in to Windows.

A per-user value under the ``Run`` registry key, so no admin rights are needed. The
installer's checkbox writes the same value, so the two can't disagree, and it shows up
(and can be turned off) in Task Manager's Startup tab.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import PureWindowsPath

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "YOMIL"


def supported() -> bool:
    return sys.platform == "win32"


def launch_command(executable: str, *, frozen: bool) -> str:
    """The command line to register: the installed ``yomil.exe``, or (from a dev
    checkout) this Python's windowless ``pythonw.exe`` running ``-m yomil``."""
    if frozen:
        return f'"{executable}" --minimized'
    exe = PureWindowsPath(executable)
    pythonw = exe.with_name("pythonw.exe") if exe.name.lower() == "python.exe" else exe
    return f'"{pythonw}" -m yomil --minimized'


def is_enabled() -> bool:
    if sys.platform != "win32":  # spelled out so mypy knows winreg exists below
        return False
    import winreg  # Windows only

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    return True


def set_enabled(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg  # Windows only

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            command = launch_command(sys.executable, frozen=getattr(sys, "frozen", False))
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, VALUE_NAME)
