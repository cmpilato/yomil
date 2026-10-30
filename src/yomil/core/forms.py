"""Shared pieces of the dialogs' pure form checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FieldMessage:
    """Shown next to a field. An error blocks saving; otherwise it's just a hint."""

    text: str
    is_error: bool
