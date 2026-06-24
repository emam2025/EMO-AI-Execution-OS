"""Base Sector Twin — shared Digital Twin logic.

Captures the common state/simulation/event pattern from EnergyTwin
and WaterTwin to eliminate ~160 lines of duplication.

Usage:
    class ManufacturingTwin(BaseSectorTwin):
        ...
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from datetime import datetime, timezone

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class BaseSectorTwin(ABC):
    """Abstract base for sector-specific digital twins.

    Provides shared implementations for state management, simulation,
    prediction, event recording, and event publishing.
    """

    def __init__(self, domain: str, event_bus: Optional[IEventBus] = None) -> None:
        self._domain = domain
        self._event_bus = event_bus
        self._states: Dict[str, Any] = {}
        self._events: Dict[str, List[Any]] = {}
        self._simulations: List[Dict[str, Any]] = []

    def _get_or_create(self, asset_id: str, state_cls: type) -> Any:
        if asset_id not in self._states:
            self._states[asset_id] = state_cls(asset_id=asset_id)
        return self._states[asset_id]

    def update_twin_state(
        self, asset_id: str, new_state: Dict[str, Any]
    ) -> Any:
        current = self._get_current_state(asset_id)
        current.state.update(new_state)
        current.version += 1
        current.last_updated = datetime.now(timezone.utc).isoformat()
        self._publish_twin_updated(asset_id, current)
        return current

    def simulate(
        self, asset_id: str, scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        current_state = self._get_current_state(asset_id)
        simulated_state = current_state.state.copy()
        simulated_state.update(scenario.get("state_changes", {}))

        result = {
            "simulated_state": simulated_state,
            "predicted_outcome": scenario.get("expected_outcome", "unknown"),
            "confidence": 0.85,
        }

        simulation = {
            "simulation_id": str(uuid4()),
            "asset_id": asset_id,
            "scenario": scenario,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._simulations.append(simulation)
        return simulation

    def predict(
        self, asset_id: str, horizon_hours: int = 24
    ) -> Dict[str, Any]:
        current_state = self._get_current_state(asset_id)
        return {
            "prediction_id": str(uuid4()),
            "asset_id": asset_id,
            "horizon_hours": horizon_hours,
            "current_state": current_state.state,
            "predicted_states": [],
            "confidence": 0.80,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_events(
        self, asset_id: str, limit: Optional[int] = None
    ) -> List[Any]:
        events = self._events.get(asset_id, [])
        if limit is not None:
            return events[-limit:]
        return events

    def get_simulations(self) -> List[Dict[str, Any]]:
        return list(self._simulations)

    def clear_state(self, asset_id: str) -> bool:
        if asset_id in self._states:
            del self._states[asset_id]
        if asset_id in self._events:
            del self._events[asset_id]
        return True

    def record_event(self, asset_id: str, event: Any) -> None:
        if asset_id not in self._events:
            self._events[asset_id] = []
        self._events[asset_id].append(event)

    def _get_current_state(self, asset_id: str) -> Any:
        return self._states.get(asset_id)

    def _publish_twin_updated(self, asset_id: str, state: Any) -> None:
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.TWIN_STATE_UPDATED,
            trace_id=f"{self._domain}-twin-{asset_id}",
            payload={
                "asset_id": asset_id,
                "version": state.version,
                "updated_fields": list(state.state.keys()),
                "domain": self._domain,
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.TWIN_STATE_UPDATED, event)
            )
        except RuntimeError:
            pass
