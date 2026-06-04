"""Phase G — ISwarmCoordinator Protocol.

Multi-agent task negotiation and conflict resolution.

LAW 8: All swarm operations are governed.
LAW 10: Workers/Agents are unreliable — always plan for fallback.
RULE 1: Deterministic resolution — same inputs → same output.

Ref: Canon LAW 8, LAW 10, RULE 1
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ISwarmCoordinator(Protocol):
    """Swarm-level coordination for multi-agent execution.

    negotiate_task(agents, task):  Select optimal agent for a task.
    coordinate_swarm(plan):        Distribute plan across agents.
    resolve_conflicts(agents):     Resolve agent conflicts.
    """

    def negotiate_task(
        self,
        agents: List[Dict[str, Any]],
        task: Dict[str, Any],
    ) -> str:
        """Negotiate which agent should execute a task.

        Returns the selected agent_id (str).
        """
        ...

    def coordinate_swarm(
        self,
        plan: Any,
    ) -> List[Dict[str, Any]]:
        """Coordinate swarm execution of a plan.

        Returns list of agent-task assignments.
        """
        ...

    def resolve_conflicts(
        self,
        agents: List[Dict[str, Any]],
    ) -> List[str]:
        """Resolve conflicts between agents.

        Returns list of resolution actions.
        """
        ...
