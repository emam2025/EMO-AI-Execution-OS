"""Event Fabric — InMemoryEventBus Implementation.

In-process pub/sub event bus with topic-based routing and async handlers.

Ref: P6.2 — InMemoryEventBus Implementation
Ref: LAW 2 (Interface Authority)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Awaitable, Callable, Dict

if TYPE_CHECKING:
    from core.models.event import EventTopic, ExecutionEvent

from core.interfaces.event_bus import IEventBus


class InMemoryEventBus(IEventBus):
    """In-memory event bus with topic-based routing."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, Dict[str, Callable[[ExecutionEvent], Awaitable[None]]]] = {}

    async def publish(self, topic: EventTopic, event: ExecutionEvent) -> None:
        """Publish event to all subscribers of the given topic."""
        topic_str = topic.value if hasattr(topic, "value") else str(topic)
        handlers_dict = self._subscribers.get(topic_str, {})

        tasks = []
        for handler in handlers_dict.values():
            result = handler(event)
            if asyncio.iscoroutine(result):
                tasks.append(result)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def subscribe(
        self,
        topic: EventTopic,
        handler: Callable[[ExecutionEvent], Awaitable[None]],
    ) -> str:
        """Subscribe to a topic. Returns subscription_id."""
        topic_str = topic.value if hasattr(topic, "value") else str(topic)

        if topic_str not in self._subscribers:
            self._subscribers[topic_str] = {}

        subscription_id = str(uuid.uuid4())
        self._subscribers[topic_str][subscription_id] = handler

        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe using subscription_id."""
        for topic_str, handlers_dict in self._subscribers.items():
            if subscription_id in handlers_dict:
                del handlers_dict[subscription_id]

                if not handlers_dict:
                    del self._subscribers[topic_str]

                return
