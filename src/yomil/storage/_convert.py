"""Python <-> SQLite column value conversions shared by the repository modules."""

from __future__ import annotations

from datetime import UTC, date, datetime


def date_or_none(value: str | None) -> date | None:
    return None if value is None else date.fromisoformat(value)


def iso_or_none(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def timestamp(value: datetime) -> str:
    """UTC ISO-8601 with a ``Z`` suffix, to the second."""
    if value.tzinfo is None:
        msg = "timestamps must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def timestamp_or_none(value: datetime | None) -> str | None:
    return None if value is None else timestamp(value)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def parse_timestamp_or_none(value: str | None) -> datetime | None:
    return None if value is None else parse_timestamp(value)
