"""Water Twin — Digital Twin Integration for Water Assets.

Manages digital twin state for treatment plants, pump stations,
and water quality sensors. Supports simulation, prediction, and
audit trail for water operations.

Ref: RC17.4.3 — Water Twin & DataPipeline Integration
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.industrial.base import BaseSectorTwin
from core.models.water import WaterOperationalEvent, WaterTwinState

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class WaterTwin(BaseSectorTwin):
    """Digital twin manager for water assets."""

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        super().__init__("water", event_bus)

    def get_twin_state(self, asset_id: str) -> WaterTwinState:
        return self._get_or_create(asset_id, WaterTwinState)

    def record_event(
        self, asset_id: str, event: WaterOperationalEvent
    ) -> None:
        super().record_event(asset_id, event)

    def get_events(
        self, asset_id: str, limit: Optional[int] = None
    ) -> List[WaterOperationalEvent]:
        return super().get_events(asset_id, limit)
