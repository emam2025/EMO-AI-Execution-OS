"""Energy Twin — Digital Twin Integration for Energy Assets.

Manages digital twin state for power plants, grid nodes, and smart meters.
Supports simulation, prediction, and audit trail for energy operations.

Ref: RC17.3 — Energy Pack Foundation
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from datetime import datetime, timezone

from core.models.energy import EnergyOperationalEvent, EnergyTwinState

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class EnergyTwin:
    """Digital twin manager for energy assets.

    Manages state, simulation, prediction, and audit trail.
    """

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus
        self._states: Dict[str, EnergyTwinState] = {}
        self._events: Dict[str, List[EnergyOperationalEvent]] = {}
        self._simulations: List[Dict[str, Any]] = []

    def get_twin_state(self, asset_id: str) -> EnergyTwinState:
        """Get current twin state for an asset."""
        if asset_id not in self._states:
            self._states[asset_id] = EnergyTwinState(asset_id=asset_id)
        return self._states[asset_id]

    def update_twin_state(
        self, asset_id: str, new_state: Dict[str, Any]
    ) -> EnergyTwinState:
        """Update twin state for an asset."""
        current = self.get_twin_state(asset_id)

        current.state.update(new_state)
        current.version += 1
        current.last_updated = datetime.now(timezone.utc).isoformat()

        self._publish_twin_updated(asset_id, current)
        return current

    def simulate(
        self, asset_id: str, scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a simulation scenario on a twin."""
        current_state = self.get_twin_state(asset_id)

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
        """Predict future state for an asset."""
        current_state = self.get_twin_state(asset_id)

        prediction = {
            "prediction_id": str(uuid4()),
            "asset_id": asset_id,
            "horizon_hours": horizon_hours,
            "current_state": current_state.state,
            "predicted_states": [],
            "confidence": 0.80,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return prediction

    def record_event(
        self, asset_id: str, event: EnergyOperationalEvent
    ) -> None:
        """Record an operational event."""
        if asset_id not in self._events:
            self._events[asset_id] = []
        self._events[asset_id].append(event)

    def get_events(
        self, asset_id: str, limit: Optional[int] = None
    ) -> List[EnergyOperationalEvent]:
        """Get operational events for an asset."""
        events = self._events.get(asset_id, [])
        if limit is not None:
            return events[-limit:]
        return events

    def get_simulations(self) -> List[Dict[str, Any]]:
        """Return all simulations."""
        return list(self._simulations)

    def clear_state(self, asset_id: str) -> bool:
        """Clear twin state and events for an asset."""
        if asset_id in self._states:
            del self._states[asset_id]
        if asset_id in self._events:
            del self._events[asset_id]
        return True

    def _publish_twin_updated(
        self, asset_id: str, state: EnergyTwinState
    ) -> None:
        """Publish a TWIN_STATE_UPDATED event."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.TWIN_STATE_UPDATED,
            trace_id=f"energy-twin-{asset_id}",
            payload={
                "asset_id": asset_id,
                "version": state.version,
                "updated_fields": list(state.state.keys()),
                "domain": "energy",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.TWIN_STATE_UPDATED, event)
            )
        except RuntimeError:
            pass
