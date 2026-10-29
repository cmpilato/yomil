"""Exceptions the UI is expected to catch and explain to the user."""


class YomilError(Exception):
    """Base class for expected, user-facing failures."""


class NotFoundError(YomilError):
    """The requested bill or payment does not exist (any more)."""


class InvalidStateError(YomilError):
    """The operation doesn't apply in the item's current state (e.g. paying a paid bill)."""


class ValidationError(YomilError):
    """An input value is not acceptable (e.g. a negative amount)."""
