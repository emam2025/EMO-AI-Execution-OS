"""F4 — TimelineExplorer: execution timeline viewer.

Tracks events per execution in chronological order, with
support for filtering by event type, service, and time range.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.observability.timeline")


class EventType(Enum):
    SUBMITTED = "submitted"
    SCHEDULED = "scheduled"
    DISPATCHED = "dispatched"
    WORKER_STARTED = "worker_started"
    WORKER_COMPLETED = "worker_completed"
    WORKER_FAILED = "worker_failed"
    RETRY = "retry"
    CANCELLED = "cancelled"
    RECONCILED = "reconciled"
    MIGRATED = "migrated"
    ESCALATED = "escalated"
    TIMEOUT = "timeout"


@dataclass
class TimelineEvent:
    timestamp: float
    event_type: EventType
    execution_id: str
    service: str = ""
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp


class Timeline:
    """Ordered event list for a single execution."""

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        self.events: List[TimelineEvent] = []

    def add_event(self, event_type: EventType, service: str = "",
                  message: str = "",
                  metadata: Optional[Dict[str, Any]] = None) -> TimelineEvent:
        event = TimelineEvent(
            timestamp=time.time(),
            event_type=event_type,
            execution_id=self.execution_id,
            service=service,
            message=message,
            metadata=metadata or {},
        )
        self.events.append(event)
        return event

    def events_since(self, timestamp: float) -> List[TimelineEvent]:
        return [e for e in self.events if e.timestamp >= timestamp]

    def filter(self, event_type: Optional[EventType] = None,
               service: Optional[str] = None) -> List[TimelineEvent]:
        result = self.events
        if event_type:
            result = [e for e in result if e.event_type == event_type]
        if service:
            result = [e for e in result if e.service == service]
        return result

    def summary(self) -> List[Dict[str, Any]]:
        return [
            {
                "time": e.timestamp,
                "age": round(e.age_seconds, 2),
                "event": e.event_type.value,
                "service": e.service,
                "message": e.message,
            }
            for e in self.events
        ]


class TimelineStore:
    """Global timeline store for all executions."""

    def __init__(self, max_executions: int = 1000):
        self._timelines: Dict[str, Timeline] = {}
        self._max_executions = max_executions

    def get_or_create(self, execution_id: str) -> Timeline:
        if execution_id not in self._timelines:
            self._evict_if_needed()
            self._timelines[execution_id] = Timeline(execution_id)
        return self._timelines[execution_id]

    def get(self, execution_id: str) -> Optional[Timeline]:
        return self._timelines.get(execution_id)

    def add_event(self, execution_id: str, event_type: EventType,
                  service: str = "", message: str = "",
                  metadata: Optional[Dict[str, Any]] = None) -> Optional[TimelineEvent]:
        tl = self.get_or_create(execution_id)
        return tl.add_event(event_type, service, message, metadata)

    def query(self, event_type: Optional[EventType] = None,
              service: Optional[str] = None,
              since: float = 0.0,
              limit: int = 100) -> List[TimelineEvent]:
        results: List[TimelineEvent] = []
        for tl in self._timelines.values():
            for e in tl.events:
                if e.timestamp < since:
                    continue
                if event_type and e.event_type != event_type:
                    continue
                if service and e.service != service:
                    continue
                results.append(e)
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    def execution_summary(self, execution_id: str) -> Optional[List[Dict[str, Any]]]:
        tl = self._timelines.get(execution_id)
        if not tl:
            return None
        return tl.summary()

    def _evict_if_needed(self) -> None:
        if len(self._timelines) < self._max_executions:
            return
        oldest = min(self._timelines.keys(),
                     key=lambda eid: self._timelines[eid].events[0].timestamp
                     if self._timelines[eid].events else 0)
        self._timelines.pop(oldest, None)

    def clear(self) -> None:
        self._timelines.clear()
