"""Event Fabric — EventStore Protocol.

Defines the contract for persistent, append-only event storage.

Ref: P6.3 — EventStore Implementation
Ref: LAW 2 (Interface Authority)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Protocol

if TYPE_CHECKING:
    from core.models.event import EventTopic, ExecutionEvent


class IEventStore(Protocol):
    """Persistent append-only log for execution events."""

    def append(self, event: ExecutionEvent) -> None:
        """Append an event to the store. MUST NOT allow updates or deletes."""
        ...

    def replay(
        self,
        topic: EventTopic,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[ExecutionEvent]:
        """Replay events for a specific topic within a time window."""
        ...

    def get_latest(self, topic: EventTopic, limit: int = 10) -> List[ExecutionEvent]:
        """Get the most recent events for a topic."""
        ...
