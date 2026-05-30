"""
Multi-Agent Society Manager — IMultiAgentSociety implementation.

Negotiates task allocation among agents, coordinates swarms, and
enforces tenant boundaries. No execution. No scheduling.
LAW-6 enforced on all public methods.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from releases.big_emo.core.interfaces.self_governance.IMultiAgentSociety import IMultiAgentSociety
from releases.big_emo.core.models.self_governance import (
    SwarmAllocation as SwarmAllocationModel,
    SwarmCoordinationState,
)


@dataclass
class AllocationPlanData:
    allocation_id: str = ""
    tenant_id: str = ""
    task_id: str = ""
    agent_assignments: List[Dict[str, Any]] = field(default_factory=list)
    coordination_state: str = "initializing"


@dataclass
class SwarmStateData:
    swarm_id: str = ""
    tenant_id: str = ""
    active_agents: int = 0
    coordination_round: int = 0
    consensus_status: str = "pending"
    pending_tasks: List[str] = field(default_factory=list)


class _TaskAllocator:
    """Internal fair task allocation logic."""

    @staticmethod
    def allocate(
        agents: List[Dict[str, Any]],
        task: Dict[str, Any],
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        required_cap = task.get("required_capability", "general")
        task_load = task.get("estimated_load", 1)
        filtered = [a for a in agents if a.get("tenant_id") in (tenant_id, "*", "")]
        scored = []
        for a in filtered:
            cap_match = 1.0 if required_cap in a.get("capabilities", []) else 0.3
            current_load = a.get("current_load", 0)
            available = 1.0 - min(current_load / 10.0, 0.9)
            score = round(cap_match * 0.6 + available * 0.4, 4)
            scored.append((score, a))
        scored.sort(key=lambda x: -x[0])
        assignments = []
        remaining = task_load
        for score, agent in scored:
            if remaining <= 0:
                break
            take = min(remaining, 5)
            assignments.append({
                "agent_id": agent.get("agent_id", ""),
                "agent_name": agent.get("name", "unknown"),
                "assigned_load": take,
                "match_score": score,
                "capability": required_cap,
            })
            remaining -= take
        return assignments


class MultiAgentSocietyManager(IMultiAgentSociety):
    """Negotiates and coordinates multi-agent task execution.

    LAW-6: every public method requires tenant_id.
    LAW-24/25: tenant boundary + resource enforcement.
    """

    def __init__(self) -> None:
        self._allocations: Dict[str, SwarmAllocationModel] = {}

    def negotiate_task(
        self,
        agents: List[Dict[str, Any]],
        task: Dict[str, Any],
        tenant_id: str,
    ) -> AllocationPlanData:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not agents:
            raise ValueError("agent list is required")
        if not task:
            raise ValueError("task is required")
        for a in agents:
            a_tid = a.get("tenant_id", "")
            if a_tid and a_tid != tenant_id and a_tid != "*":
                raise ValueError(f"Agent {a.get('agent_id')} belongs to different tenant (LAW-24)")
        allocation_id = f"alloc-{uuid.uuid4().hex[:16]}"
        assignments = _TaskAllocator.allocate(agents, task, tenant_id)
        plan = AllocationPlanData(
            allocation_id=allocation_id,
            tenant_id=tenant_id,
            task_id=task.get("task_id", f"task-{uuid.uuid4().hex[:12]}"),
            agent_assignments=assignments,
            coordination_state=SwarmCoordinationState.NEGOTIATING.value,
        )
        model = SwarmAllocationModel(
            allocation_id=allocation_id,
            tenant_id=tenant_id,
            task_id=plan.task_id,
            agent_assignments=assignments,
            coordination_state=SwarmCoordinationState.NEGOTIATING,
        )
        self._allocations[allocation_id] = model
        return plan

    def coordinate_swarm(
        self,
        plan: Dict[str, Any],
        tenant_id: str,
    ) -> SwarmStateData:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        assignments = plan.get("agent_assignments", [])
        swarm_id = f"swarm-{uuid.uuid4().hex[:16]}"
        pending = [
            f"{a.get('agent_id', '?')}:{a.get('assigned_load', 0)}" for a in assignments
        ]
        state = SwarmStateData(
            swarm_id=swarm_id,
            tenant_id=tenant_id,
            active_agents=len(assignments),
            coordination_round=1,
            consensus_status="consensus_reached" if assignments else "pending",
            pending_tasks=pending if len(pending) > 1 else [],
        )
        alloc_id = plan.get("allocation_id", "")
        if alloc_id in self._allocations:
            existing = self._allocations[alloc_id]
            existing.coordination_state = SwarmCoordinationState.EXECUTING
        return state

    def enforce_tenant_boundaries(
        self,
        plan: Dict[str, Any],
        tenant_id: str,
    ) -> bool:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        plan_tid = plan.get("tenant_id", "")
        if plan_tid and plan_tid != tenant_id:
            return False
        for a in plan.get("agent_assignments", []):
            agent_tid = a.get("tenant_id", a.get("agent_id", "")).split("-")[0]
        return True

    def get_allocation(
        self,
        allocation_id: str,
        tenant_id: str,
    ) -> SwarmAllocationModel:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        alloc = self._allocations.get(allocation_id)
        if not alloc or alloc.tenant_id != tenant_id:
            raise KeyError(f"Allocation not found: {allocation_id}")
        return alloc
