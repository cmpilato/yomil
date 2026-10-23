"""Where YOMIL keeps its files on disk."""

from pathlib import Path

from platformdirs import user_data_path, user_log_path

APP_NAME = "YOMIL"


def data_dir() -> Path:
    """Directory holding the database and backups (``%LOCALAPPDATA%\\YOMIL`` on Windows)."""
    path = user_data_path(APP_NAME, appauthor=False, ensure_exists=True)
    return Path(path)


def default_db_path() -> Path:
    return data_dir() / "yomil.sqlite3"


def log_dir() -> Path:
    return Path(user_log_path(APP_NAME, appauthor=False, ensure_exists=True))
