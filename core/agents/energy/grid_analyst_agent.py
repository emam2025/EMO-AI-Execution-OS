"""Grid Analyst Agent — Grid Operations Analysis.

Analyzes grid stability, load distribution, and capacity planning.
Observe-only: recommends, never controls grid operations.

Ref: RC17.3 — Energy Pack Foundation
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.models.agent import (
    AgentAudit,
    AgentCost,
    AgentIdentity,
    AgentMemory,
    AgentPermissions,
    AgentRisk,
    AgentSkills,
)

if TYPE_CHECKING:
    from core.governance.energy_safety import EnergySafetyGate
    from core.interfaces.agents import IAgentApprovalGate
    from core.interfaces.event_bus import IEventBus
    from core.industrial.energy_twin import EnergyTwin


class GridAnalystAgent:
    """Grid operations analysis agent.

    Analyzes grid stability, load distribution, and capacity planning.
    All actions are observe/recommend in V1.
    """

    def __init__(
        self,
        identity: AgentIdentity,
        energy_twin: Optional[EnergyTwin] = None,
        event_bus: Optional[IEventBus] = None,
        approval_gate: Optional[IAgentApprovalGate] = None,
        safety_gate: Optional[EnergySafetyGate] = None,
    ) -> None:
        self._identity = identity
        self._energy_twin = energy_twin
        self._event_bus = event_bus
        self._approval_gate = approval_gate
        self._safety_gate = safety_gate
        self._memory = AgentMemory()
        self._skills = AgentSkills(registered_tools=["grid_analysis"])
        self._permissions = AgentPermissions(
            allowed_actions=[
                "analyze_grid_stability",
                "analyze_load_distribution",
                "recommend_capacity",
            ],
            requires_approval_for=[],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    @property
    def memory(self) -> AgentMemory:
        return self._memory

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

    def analyze_stability(self, node_ids: List[str]) -> Dict[str, Any]:
        """Analyze grid stability across nodes."""
        node_analysis: List[Dict[str, Any]] = []
        for nid in node_ids:
            if self._energy_twin is not None:
                twin_state = self._energy_twin.get_twin_state(nid)
                current_load = twin_state.state.get("current_load_mw", 0.0)
                max_capacity = twin_state.state.get("max_capacity_mw", 0.0)
                utilization = (current_load / max_capacity * 100) if max_capacity > 0 else 0.0
                status = twin_state.state.get("status", "unknown")
            else:
                current_load = 0.0
                max_capacity = 0.0
                utilization = 0.0
                status = "unknown"

            node_analysis.append({
                "node_id": nid,
                "current_load_mw": current_load,
                "max_capacity_mw": max_capacity,
                "utilization_pct": round(utilization, 2),
                "status": status,
                "stable": utilization < 90.0,
            })

        overall_stable = all(n["stable"] for n in node_analysis)
        return {
            "nodes": node_analysis,
            "overall_stable": overall_stable,
            "recommendation": "stable" if overall_stable else "capacity_rebalance_needed",
        }

    def analyze_load_distribution(
        self, node_ids: List[str]
    ) -> Dict[str, Any]:
        """Analyze load distribution across nodes."""
        loads: Dict[str, float] = {}
        for nid in node_ids:
            if self._energy_twin is not None:
                twin_state = self._energy_twin.get_twin_state(nid)
                loads[nid] = twin_state.state.get("current_load_mw", 0.0)
            else:
                loads[nid] = 0.0

        total = sum(loads.values())
        avg = total / len(loads) if loads else 0.0
        max_node = max(loads, key=loads.get) if loads else None
        min_node = min(loads, key=loads.get) if loads else None

        return {
            "loads": loads,
            "total_load_mw": total,
            "average_load_mw": round(avg, 2),
            "max_node": max_node,
            "min_node": min_node,
            "balanced": all(
                abs(v - avg) / avg < 0.2 if avg > 0 else True
                for v in loads.values()
            ),
        }

    def recommend_capacity(self, node_id: str) -> Dict[str, Any]:
        """Recommend capacity adjustment for a node."""
        if self._energy_twin is not None:
            twin_state = self._energy_twin.get_twin_state(node_id)
            current_load = twin_state.state.get("current_load_mw", 0.0)
            max_capacity = twin_state.state.get("max_capacity_mw", 0.0)
            utilization = (current_load / max_capacity * 100) if max_capacity > 0 else 0.0

            if utilization > 85.0:
                return {
                    "node_id": node_id,
                    "recommendation": "increase_capacity",
                    "current_utilization": round(utilization, 2),
                    "suggested_capacity_mw": max_capacity * 1.25,
                }
            elif utilization < 30.0:
                return {
                    "node_id": node_id,
                    "recommendation": "reduce_capacity",
                    "current_utilization": round(utilization, 2),
                    "suggested_capacity_mw": max_capacity * 0.75,
                }

        return {
            "node_id": node_id,
            "recommendation": "no_change",
            "current_utilization": 0.0,
        }

    def recommend_load_shedding(
        self, grid_id: str, trust_level: str = "UNVERIFIED"
    ) -> Dict[str, Any]:
        """Recommend load shedding for a grid node.

        Evaluates through EnergySafetyGate. If LOAD_SHEDDING is blocked,
        publishes SAFETY_VIOLATION event via EventBus.
        """
        current_load = 0.0
        max_capacity = 0.0
        if self._energy_twin is not None:
            twin_state = self._energy_twin.get_twin_state(grid_id)
            current_load = twin_state.state.get("current_load_mw", 0.0)
            max_capacity = twin_state.state.get("max_capacity_mw", 0.0)

        utilization = (current_load / max_capacity * 100) if max_capacity > 0 else 0.0
        needs_shedding = utilization > 90.0

        recommendation: Dict[str, Any] = {
            "grid_id": grid_id,
            "current_load_mw": current_load,
            "max_capacity_mw": max_capacity,
            "utilization_pct": round(utilization, 2),
            "needs_load_shedding": needs_shedding,
        }

        if needs_shedding and self._safety_gate is not None:
            from core.models.energy_policy import EnergyActionType

            decision = self._safety_gate.evaluate(
                action_type=EnergyActionType.LOAD_SHEDDING,
                trust_level=trust_level,
                context={"grid_id": grid_id, "utilization": utilization},
            )
            recommendation["safety_allowed"] = decision.allowed
            recommendation["safety_reason"] = decision.reason
            recommendation["requires_approval"] = decision.requires_approval

            if not decision.allowed:
                recommendation["recommendation"] = "load_shedding_blocked"
                self._publish_safety_violation(grid_id, decision.reason, {
                    "utilization": utilization,
                    "trust_level": trust_level,
                })
            else:
                recommendation["recommendation"] = "load_shedding_recommended"
        elif needs_shedding:
            recommendation["recommendation"] = "load_shedding_recommended"
            recommendation["safety_allowed"] = None
            recommendation["safety_reason"] = "no_safety_gate"
        else:
            recommendation["recommendation"] = "no_action_needed"
            recommendation["safety_allowed"] = None
            recommendation["safety_reason"] = "utilization_normal"

        if self._event_bus is not None:
            self._publish_analyze_event("recommend_load_shedding", grid_id, recommendation)

        self._audit.record_action(
            action="load_shedding.recommended",
            context={"agent_id": self._identity.id, "grid_id": grid_id},
            result={"recommendation": recommendation.get("recommendation")},
        )
        return recommendation

    def _publish_analyze_event(
        self, operation: str, asset_id: str, result: Dict[str, Any]
    ) -> None:
        """Publish an ANALYZE event via EventBus."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.AGENT_STATE_CHANGED,
            trace_id=f"grid-analyst-{operation}-{asset_id}",
            payload={
                "agent_id": self._identity.id,
                "operation": operation,
                "asset_id": asset_id,
                "result": result,
                "domain": "energy",
                "action_type": "ANALYZE",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(EventTopic.AGENT_STATE_CHANGED, event))
        except RuntimeError:
            pass

    def _publish_safety_violation(
        self, grid_id: str, reason: str, context: Dict[str, Any]
    ) -> None:
        """Publish a SAFETY_VIOLATION event via EventBus."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.SAFETY_VIOLATION,
            trace_id=f"grid-analyst-violation-{grid_id}",
            payload={
                "agent_id": self._identity.id,
                "grid_id": grid_id,
                "reason": reason,
                "context": context,
                "domain": "energy",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.SAFETY_VIOLATION, event)
            )
        except RuntimeError:
            pass
