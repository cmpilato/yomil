"""YOMIL: recurring bill reminders with manual reconciliation."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("yomil")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
