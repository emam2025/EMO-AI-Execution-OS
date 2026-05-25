import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.models.events import ExecutionEvent


class EventStore:
    """Persistent append-only log of execution events.

    Writes to a JSON-lines file for durability. Used as the
    foundation for replay, CodeGraph feed, and audit trails.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or os.path.join(
            os.path.dirname(__file__), "..", "..", "artifacts", "events.jsonl"
        )
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: ExecutionEvent) -> None:
        record = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "source": event.source,
            "payload": event.payload,
            "trace_id": event.trace_id,
            "session_id": event.session_id,
            "_stored_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            with open(self._path, "a") as f:
                f.write(json.dumps(record) + "\n")

    def replay(self, session_id: Optional[str] = None) -> List[ExecutionEvent]:
        if not os.path.exists(self._path):
            return []
        events: List[ExecutionEvent] = []
        with self._lock:
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if session_id and record.get("session_id") != session_id:
                        continue
                    events.append(
                        ExecutionEvent(
                            event_id=record["event_id"],
                            event_type=record["event_type"],
                            timestamp=record["timestamp"],
                            source=record["source"],
                            payload=record.get("payload", {}),
                            trace_id=record.get("trace_id", ""),
                            session_id=record.get("session_id", ""),
                        )
                    )
        return events

    def clear(self) -> None:
        with self._lock:
            if os.path.exists(self._path):
                os.remove(self._path)
