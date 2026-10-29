"""Helpers for building audit-log details."""

from __future__ import annotations

import enum
from dataclasses import fields
from datetime import UTC, date, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def jsonable(value: object) -> Any:
    """Turn a model field value into something ``json.dumps`` accepts."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [jsonable(v) for v in value]
    return value


def snapshot(obj: Any, *, skip: tuple[str, ...] = ("id",)) -> dict[str, Any]:
    """All fields of a model dataclass, JSON-ready."""
    return {f.name: jsonable(getattr(obj, f.name)) for f in fields(obj) if f.name not in skip}


def diff(old: Any, new: Any) -> dict[str, list[Any]]:
    """``{field: [old, new]}`` for each field that differs between two model dataclasses."""
    changes: dict[str, list[Any]] = {}
    for f in fields(old):
        before, after = getattr(old, f.name), getattr(new, f.name)
        if before != after:
            changes[f.name] = [jsonable(before), jsonable(after)]
    return changes
