"""Industrial Intelligence Fabric — Twin Manager.

Manages digital twin state, simulation, and event recording.

Ref: RC16.9.3 — TwinManager Implementation
Ref: LAW 2 (Interface Authority)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from datetime import datetime, timezone

from core.models.industrial import OperationalEvent, TwinState

if TYPE_CHECKING:
    from core.interfaces.industrial import IAssetManager
    from core.interfaces.event_bus import IEventBus
    from core.models.event import EventTopic, ExecutionEvent

from core.interfaces.industrial import ITwinManager


class TwinManager(ITwinManager):
    """Manages digital twin state and simulation."""

    def __init__(
        self,
        asset_manager: Optional[IAssetManager] = None,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._states: Dict[str, TwinState] = {}
        self._events: Dict[str, List[OperationalEvent]] = {}
        self._am = asset_manager
        self._event_bus = event_bus

    def get_twin_state(self, asset_id: str) -> TwinState:
        """Get current twin state for an asset."""
        if asset_id not in self._states:
            # Initialize with empty state
            self._states[asset_id] = TwinState(asset_id=asset_id)
        return self._states[asset_id]

    def update_twin_state(self, asset_id: str, new_state: Dict[str, Any]) -> TwinState:
        """Update twin state for an asset."""
        current = self.get_twin_state(asset_id)

        # Update state and increment version
        current.state.update(new_state)
        current.version += 1
        current.last_updated = datetime.now(timezone.utc).isoformat()

        # Publish event synchronously if event_bus is available
        if self._event_bus is not None:
            import asyncio
            from core.models.event import EventTopic, ExecutionEvent

            event = ExecutionEvent(
                topic=EventTopic.TWIN_STATE_UPDATED,
                trace_id=f"twin-{asset_id}",
                payload={
                    "asset_id": asset_id,
                    "version": current.version,
                    "updated_fields": list(new_state.keys()),
                },
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._event_bus.publish(EventTopic.TWIN_STATE_UPDATED, event))
            except RuntimeError:
                pass

        return current

    def simulate(
        self, asset_id: str, scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a simulation scenario on a twin.

        Returns:
            {
                "simulation_id": str,
                "asset_id": str,
                "scenario": dict,
                "result": dict,
                "timestamp": str
            }
        """
        # Validate asset exists (if asset_manager provided)
        if self._am is not None:
            asset = self._am.get_asset(asset_id)
            if asset is None:
                raise ValueError(f"Asset not found: {asset_id}")

        # Simple simulation logic (can be extended)
        current_state = self.get_twin_state(asset_id)

        # Apply scenario to state (mock simulation)
        simulated_state = current_state.state.copy()
        simulated_state.update(scenario.get("state_changes", {}))

        # Generate result (mock)
        result = {
            "simulated_state": simulated_state,
            "predicted_outcome": scenario.get("expected_outcome", "unknown"),
            "confidence": 0.85,  # Mock confidence
        }

        return {
            "simulation_id": str(uuid.uuid4()),
            "asset_id": asset_id,
            "scenario": scenario,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def record_event(self, asset_id: str, event: OperationalEvent) -> None:
        """Record an operational event."""
        if asset_id not in self._events:
            self._events[asset_id] = []

        self._events[asset_id].append(event)

    def get_events(self, asset_id: str, limit: Optional[int] = None) -> List[OperationalEvent]:
        """Get operational events for an asset."""
        events = self._events.get(asset_id, [])
        if limit is not None:
            return events[-limit:]  # Return last N events
        return events

    def clear_state(self, asset_id: str) -> bool:
        """Clear twin state and events for an asset."""
        if asset_id in self._states:
            del self._states[asset_id]
        if asset_id in self._events:
            del self._events[asset_id]
        return True
