"""Repository functions for the append-only ``event_log`` table."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from yomil.core.models import Action, Entity, EventLogEntry
from yomil.storage._convert import parse_timestamp, timestamp

if TYPE_CHECKING:
    import sqlite3
    from datetime import datetime


def append(
    conn: sqlite3.Connection,
    entity: Entity,
    entity_id: int,
    action: Action,
    detail: dict[str, Any],
    at: datetime,
) -> None:
    conn.execute(
        "INSERT INTO event_log (at, entity, entity_id, action, detail_json) VALUES (?, ?, ?, ?, ?)",
        (timestamp(at), entity.value, entity_id, action.value, json.dumps(detail, sort_keys=True)),
    )


def for_entity(conn: sqlite3.Connection, entity: Entity, entity_id: int) -> list[EventLogEntry]:
    """Entries about one series or occurrence, oldest first."""
    rows = conn.execute(
        "SELECT * FROM event_log WHERE entity = ? AND entity_id = ? ORDER BY at, id",
        (entity.value, entity_id),
    )
    return [
        EventLogEntry(
            id=r["id"],
            at=parse_timestamp(r["at"]),
            entity=Entity(r["entity"]),
            entity_id=r["entity_id"],
            action=Action(r["action"]),
            detail=json.loads(r["detail_json"]),
        )
        for r in rows
    ]
