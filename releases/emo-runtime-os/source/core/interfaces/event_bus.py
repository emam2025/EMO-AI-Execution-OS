from typing import Any, Callable, Dict, List, Protocol

from ..models.events import ExecutionEvent


EventHandler = Callable[[ExecutionEvent], None]


class IEventBus(Protocol):

    def publish(self, topic: str, event: ExecutionEvent) -> None:
        ...

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        ...

    def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        ...

    def get_events(self, topic: str, limit: int = 100) -> List[ExecutionEvent]:
        ...

    def get_all_events(self, limit: int = 100) -> List[ExecutionEvent]:
        ...

    def clear(self) -> None:
        ...
