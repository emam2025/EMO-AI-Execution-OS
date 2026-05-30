"""
Strategic Planning Protocol — IStrategicPlanner (Interface Only).

Defines the contract for decomposing high-level goals into executable
DAG plans. No implementation, no scheduling, no execution.

LAW-6: every public method requires tenant_id.
LAW-11: every result is scoped by tenant_id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class PlanHypothesis(Protocol):
    """Read-only view of a planning hypothesis."""

    hypothesis_id: str
    tenant_id: str
    goal_id: str
    dag_blueprint: Dict[str, Any]
    confidence_score: float
    validator_signature: str


class IStrategicPlanner(ABC):
    """Contract for decomposing goals into actionable DAG plans.

    No mutation of R2/R3 memory or any runtime state.
    """

    @abstractmethod
    def decompose_goal(
        self,
        goal: str,
        tenant_id: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> PlanHypothesis:
        """Decompose a high-level goal into a DAG execution plan.

        Args:
            goal:        Natural-language goal description.
            tenant_id:   LAW-6 mandatory tenant scope.
            constraints: Optional resource/time/quality bounds.

        Returns:
            PlanHypothesis with dag_blueprint and confidence_score.
        """
        ...

    @abstractmethod
    def evaluate_feasibility(
        self,
        plan: Dict[str, Any],
        tenant_id: str,
    ) -> bool:
        """Evaluate whether a plan is feasible given current context.

        Args:
            plan:       The dag_blueprint to evaluate.
            tenant_id:  LAW-6 mandatory tenant scope.

        Returns:
            True if the plan is structurally and contextually feasible.
        """
        ...

    @abstractmethod
    def list_active_plans(
        self,
        tenant_id: str,
        project_id: str = "",
        limit: int = 10,
    ) -> List[str]:
        """Return hypothesis_ids of active plans.

        LAW-11: results are filtered by tenant_id + project_id.
        """
        ...
