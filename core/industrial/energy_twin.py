"""Energy Twin — Digital Twin Integration for Energy Assets.

Manages digital twin state for power plants, grid nodes, and smart meters.
Supports simulation, prediction, and audit trail for energy operations.

Ref: RC17.3 — Energy Pack Foundation
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.industrial.base import BaseSectorTwin
from core.models.energy import EnergyOperationalEvent, EnergyTwinState

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class EnergyTwin(BaseSectorTwin):
    """Digital twin manager for energy assets."""

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        super().__init__("energy", event_bus)

    def get_twin_state(self, asset_id: str) -> EnergyTwinState:
        return self._get_or_create(asset_id, EnergyTwinState)

    def record_event(
        self, asset_id: str, event: EnergyOperationalEvent
    ) -> None:
        super().record_event(asset_id, event)

    def get_events(
        self, asset_id: str, limit: Optional[int] = None
    ) -> List[EnergyOperationalEvent]:
        return super().get_events(asset_id, limit)
