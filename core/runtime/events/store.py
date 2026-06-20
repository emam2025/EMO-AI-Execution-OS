"""Event Fabric — SQLiteEventStore Implementation.

Persistent append-only log using SQLite with WAL mode for concurrent reads.

Ref: P6.3 — EventStore Implementation
Ref: LAW 6 (Shared Models MUST NOT live inside runtime engines)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.interfaces.event_store import IEventStore
from core.models.event import EventMetadata, EventTopic, ExecutionEvent


class SQLiteEventStore(IEventStore):
    """SQLite-based append-only event store."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database with WAL mode and events table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    topic TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    metadata TEXT
                )
            """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")

    def append(self, event: ExecutionEvent) -> None:
        """Append an event to the store."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO events (event_id, topic, trace_id, timestamp, payload, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.topic.value if hasattr(event.topic, "value") else str(event.topic),
                    event.trace_id,
                    event.timestamp.isoformat(),
                    json.dumps(event.payload),
                    json.dumps(
                        {"source": event.metadata.source, "worker_id": event.metadata.worker_id, "custom_tags": event.metadata.custom_tags}
                    )
                    if event.metadata
                    else None,
                ),
            )

    def replay(
        self,
        topic: EventTopic,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[ExecutionEvent]:
        """Replay events for a specific topic within a time window."""
        topic_str = topic.value if hasattr(topic, "value") else str(topic)
        query = "SELECT event_id, topic, trace_id, timestamp, payload, metadata FROM events WHERE topic = ?"
        params: List = [topic_str]

        if start_time is not None:
            start_dt = datetime.fromtimestamp(start_time, tz=timezone.utc)
            query += " AND timestamp >= ?"
            params.append(start_dt.isoformat())
        if end_time is not None:
            end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)
            query += " AND timestamp <= ?"
            params.append(end_dt.isoformat())

        query += " ORDER BY timestamp ASC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

        return [
            ExecutionEvent(
                event_id=row["event_id"],
                topic=EventTopic(row["topic"]),
                trace_id=row["trace_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                payload=json.loads(row["payload"]),
                metadata=EventMetadata(**json.loads(row["metadata"])) if row["metadata"] else None,
            )
            for row in rows
        ]

    def get_latest(self, topic: EventTopic, limit: int = 10) -> List[ExecutionEvent]:
        """Get the most recent events for a topic (descending order)."""
        topic_str = topic.value if hasattr(topic, "value") else str(topic)
        query = "SELECT event_id, topic, trace_id, timestamp, payload, metadata FROM events WHERE topic = ? ORDER BY timestamp DESC LIMIT ?"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (topic_str, limit)).fetchall()

        return [
            ExecutionEvent(
                event_id=row["event_id"],
                topic=EventTopic(row["topic"]),
                trace_id=row["trace_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                payload=json.loads(row["payload"]),
                metadata=EventMetadata(**json.loads(row["metadata"])) if row["metadata"] else None,
            )
            for row in rows
        ]
