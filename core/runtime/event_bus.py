from collections import defaultdict
from typing import Any, Callable, Dict, List

from core.interfaces.event_bus import IEventBus
from core.models.events import ExecutionEvent

EventHandler = Callable[[ExecutionEvent], None]


class InMemoryEventBus(IEventBus):
    """In-process pub/sub event bus.

    Thread-safe for single-threaded usage. For multi-threaded
    environments, wrap calls with a lock.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._history: Dict[str, List[ExecutionEvent]] = defaultdict(list)
        self._global_history: List[ExecutionEvent] = []

    def publish(self, topic: str, event: ExecutionEvent) -> None:
        self._history[topic].append(event)
        self._global_history.append(event)
        for handler in self._handlers.get(topic, []):
            try:
                handler(event)
            except Exception:
                pass  # Isolate subscriber failures per CHAOS-001

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        if handler not in self._handlers[topic]:
            self._handlers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        self._handlers[topic] = [
            h for h in self._handlers[topic] if h is not handler
        ]

    def get_events(self, topic: str, limit: int = 100) -> List[ExecutionEvent]:
        return self._history[topic][-limit:]

    def get_all_events(self, limit: int = 100) -> List[ExecutionEvent]:
        return self._global_history[-limit:]

    def clear(self) -> None:
        self._handlers.clear()
        self._history.clear()
        self._global_history.clear()
