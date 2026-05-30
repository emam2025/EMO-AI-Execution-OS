"""CanaryLauncher — activates strict_canary_mode and injects CanaryObserver."""

# LAW-5: Observable — canary launch publishes event to F4 Observability
# LAW-11: No Global State — each session creates fresh observer
# LAW-12: Traceable — canary_trace_id links user → session → DAG → metrics → replay

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Optional

from scripts.canary.canary_config import CanaryConfig, DEFAULT_CANARY_CONFIG
from scripts.canary.canary_observer import CanaryObserver


class CanaryLauncher:
    def __init__(
        self,
        config: Optional[CanaryConfig] = None,
        event_bus: Any = None,
    ):
        self._config = config or DEFAULT_CANARY_CONFIG
        self._event_bus = event_bus
        self._active_observers: Dict[str, CanaryObserver] = {}

    @property
    def strict_canary_mode(self) -> bool:
        return self._config.strict_canary_mode

    @property
    def config(self) -> CanaryConfig:
        return self._config

    def launch_session(self, user_id: str) -> CanaryObserver:
        user = self._config.user_map.get(user_id)
        if user is None:
            raise ValueError(
                f"Unknown canary user: {user_id}. "
                f"Available: {list(self._config.user_map.keys())}"
            )

        raw = f"canary_{user_id}_{time.time_ns()}_{len(self._active_observers)}"
        trace_id = "cny_" + hashlib.sha256(raw.encode()).hexdigest()[:28]

        observer = CanaryObserver(
            event_bus=self._event_bus,
            canary_trace_id=trace_id,
        )
        self._active_observers[user_id] = observer

        if self._event_bus is not None:
            try:
                from core.models.events import ExecutionEvent, EventType
                event = ExecutionEvent(
                    event_id=trace_id[:16],
                    event_type=EventType.STATE_TRANSITION,
                    timestamp_ns=time.time_ns(),
                    payload={
                        "action": "canary_session_started",
                        "user_id": user_id,
                        "canary_trace_id": trace_id,
                        "worker_pool": user.worker_pool_label,
                        "isolated_repo": user.isolated_repo_path,
                        "strict_canary_mode": self._config.strict_canary_mode,
                    },
                )
                self._event_bus.publish("runtime.canary.sessions", event)
            except Exception:
                pass

        return observer

    def get_observer(self, user_id: str) -> Optional[CanaryObserver]:
        return self._active_observers.get(user_id)

    def end_session(self, user_id: str) -> Optional[CanaryObserver]:
        observer = self._active_observers.pop(user_id, None)
        if observer is not None and self._event_bus is not None:
            try:
                from core.models.events import ExecutionEvent, EventType
                event = ExecutionEvent(
                    event_id=observer.canary_trace_id[:16],
                    event_type=EventType.STATE_TRANSITION,
                    timestamp_ns=time.time_ns(),
                    payload={
                        "action": "canary_session_ended",
                        "user_id": user_id,
                        "canary_trace_id": observer.canary_trace_id,
                    },
                )
                self._event_bus.publish("runtime.canary.sessions", event)
            except Exception:
                pass
        return observer

    def get_active_sessions(self) -> Dict[str, CanaryObserver]:
        return dict(self._active_observers)
