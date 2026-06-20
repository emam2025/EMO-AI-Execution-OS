"""OEEMonitorAgent — Real-time OEE Monitoring Dashboard Integration.

Accumulates production cycles in rolling windows, calculates OEE via
OEECalculator (RC17.2.1), publishes OEE_CALCULATED events, and exposes
current OEE state for dashboard consumption.

Ref: RC17.2.4 — OEE Monitor Agent (Real-time Dashboard Integration)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from core.models.agent import (
    AgentAudit,
    AgentIdentity,
    AgentMemory,
    AgentPermissions,
    AgentSkills,
)
from core.models.manufacturing_advanced import OEEState

if TYPE_CHECKING:
    from core.industrial.oee_engine import OEECalculator
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


@dataclass
class _AssetProductionState:
    """Accumulated production metrics for a single asset."""

    planned_time: float = 0.0
    run_time: float = 0.0
    total_count: int = 0
    good_count: int = 0
    ideal_rate: float = 1.0
    cycle_count: int = 0


class OEEMonitorAgent:
    """OEE monitor agent — real-time dashboard integration.

    Accumulates production cycles per asset, delegates OEE calculation
    to OEECalculator, publishes OEE_CALCULATED events, and exposes
    current OEE state for dashboard or other agents.
    """

    def __init__(
        self,
        identity: AgentIdentity,
        oee_calculator: OEECalculator,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._identity = identity
        self._oee_calculator = oee_calculator
        self._event_bus = event_bus
        self._memory = AgentMemory()
        self._skills = AgentSkills(
            registered_tools=["oee_calculator", "production_monitor"]
        )
        self._permissions = AgentPermissions(
            allowed_actions=[
                "record_production_cycle",
                "get_current_oee",
                "get_asset_metrics",
            ],
            requires_approval_for=[],
        )
        self._audit = AgentAudit()
        self._status = "created"
        self._asset_states: Dict[str, _AssetProductionState] = {}
        self._latest_oee: Dict[str, OEEState] = {}

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    @property
    def skills(self) -> AgentSkills:
        return self._skills

    @property
    def permissions(self) -> AgentPermissions:
        return self._permissions

    @property
    def audit(self) -> AgentAudit:
        return self._audit

    def activate(self) -> None:
        self._status = "active"
        self._audit.record_action(
            action="agent.activate",
            context={"agent_id": self._identity.id},
            result={"status": "active"},
        )

    def suspend(self, reason: str) -> None:
        self._status = "suspended"
        self._audit.record_action(
            action="agent.suspend",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "suspended"},
        )

    def terminate(self, reason: str) -> None:
        self._status = "terminated"
        self._audit.record_action(
            action="agent.terminate",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "terminated"},
        )

    def record_production_cycle(
        self,
        asset_id: str,
        run_time_mins: float,
        total_count: int,
        good_count: int,
        ideal_rate: float,
    ) -> OEEState:
        """Record a production cycle and recalculate OEE for the asset."""
        state = self._asset_states.setdefault(asset_id, _AssetProductionState())
        state.run_time += run_time_mins
        state.total_count += total_count
        state.good_count += good_count
        state.ideal_rate = ideal_rate
        state.planned_time += run_time_mins
        state.cycle_count += 1

        metrics = self._build_metrics(state)
        oee_state = self._oee_calculator.calculate_oee(asset_id, metrics)
        self._latest_oee[asset_id] = oee_state

        self._audit.record_action(
            action="oee.cycle.recorded",
            context={
                "agent_id": self._identity.id,
                "asset_id": asset_id,
                "cycle_number": state.cycle_count,
                "overall_oee_pct": oee_state.overall_oee_pct,
            },
            result={
                "availability_pct": oee_state.availability_pct,
                "performance_pct": oee_state.performance_pct,
                "quality_pct": oee_state.quality_pct,
                "overall_oee_pct": oee_state.overall_oee_pct,
            },
        )

        return oee_state

    def get_current_oee(self, asset_id: str) -> Optional[OEEState]:
        """Return the latest OEE state for an asset, or None if not tracked."""
        return self._latest_oee.get(asset_id)

    def get_asset_metrics(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Return accumulated raw metrics for an asset."""
        state = self._asset_states.get(asset_id)
        if state is None:
            return None
        return {
            "asset_id": asset_id,
            "run_time": state.run_time,
            "total_count": state.total_count,
            "good_count": state.good_count,
            "ideal_rate": state.ideal_rate,
            "cycle_count": state.cycle_count,
        }

    @staticmethod
    def _build_metrics(state: _AssetProductionState):
        """Build ProductionMetrics from accumulated state."""
        from core.industrial.oee_engine import ProductionMetrics

        return ProductionMetrics(
            planned_production_time_minutes=state.planned_time,
            run_time_minutes=state.run_time,
            total_count=state.total_count,
            good_count=state.good_count,
            ideal_run_rate_per_minute=state.ideal_rate,
        )
