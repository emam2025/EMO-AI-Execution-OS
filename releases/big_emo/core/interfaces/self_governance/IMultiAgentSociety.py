"""
Multi-Agent Society Protocol — IMultiAgentSociety (Interface Only).

Defines the contract for task negotiation, hierarchical coordination,
and swarm management among permanent agents. No implementation.

LAW-8:  no cross-tenant agent coordination.
LAW-24: agent assignments must respect tenant boundaries.
LAW-25: swarm coordination must not exceed allocated resources.
LAW-26: agent negotiation must be auditable.
LAW-27: all agent actions must be traceable to a tenant context.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class AllocationPlan(Protocol):
    """Read-only view of a task allocation among agents."""

    allocation_id: str
    tenant_id: str
    task_id: str
    agent_assignments: List[Dict[str, Any]]
    coordination_state: str


@runtime_checkable
class SwarmState(Protocol):
    """Read-only view of a swarm coordination state."""

    swarm_id: str
    tenant_id: str
    active_agents: int
    coordination_round: int
    consensus_status: str
    pending_tasks: List[str]


class IMultiAgentSociety(ABC):
    """Contract for multi-agent task negotiation and swarm coordination.

    All operations scoped by tenant_id. No cross-tenant leakage.
    """

    @abstractmethod
    def negotiate_task(
        self,
        agents: List[Dict[str, Any]],
        task: Dict[str, Any],
        tenant_id: str,
    ) -> AllocationPlan:
        """Negotiate task allocation among available agents.

        Args:
            agents:    List of available agent descriptors.
            task:      Task description with requirements and constraints.
            tenant_id: LAW-6 mandatory tenant scope.

        Returns:
            AllocationPlan with agent assignments and coordination state.
        """
        ...

    @abstractmethod
    def coordinate_swarm(
        self,
        plan: Dict[str, Any],
        tenant_id: str,
    ) -> SwarmState:
        """Coordinate a swarm to execute an allocation plan.

        Args:
            plan:       AllocationPlan dict to execute.
            tenant_id:  LAW-6 mandatory tenant scope.

        Returns:
            SwarmState with active agents, coordination round, and consensus.
        """
        ...
