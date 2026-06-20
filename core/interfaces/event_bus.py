"""EventBus Protocol for execution event stream.

Protocol-only interface. No implementation.

Ref: P6.1 — Event Domain Models & EventBus Protocol
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable, Protocol

if TYPE_CHECKING:
    from core.models.event import EventTopic, ExecutionEvent


class IEventBus(Protocol):
    """Protocol for publish/subscribe event bus.

    Supports topic-based routing with async handlers.
    """

    def publish(self, topic: EventTopic, event: ExecutionEvent) -> None:
        """Publish an event to a topic."""
        ...

    def subscribe(
        self,
        topic: EventTopic,
        handler: Callable[[ExecutionEvent], Awaitable[None]],
    ) -> str:
        """Subscribe a handler to a topic. Returns subscription_id."""
        ...

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription by ID."""
        ...
