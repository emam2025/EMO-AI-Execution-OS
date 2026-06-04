"""Phase G — ICognitiveOrchestrator Protocol.

Top-level routing facade for cognitive orchestration.
Routes intents through planning, critique, optimization,
and submits to UnifiedRuntimeAPI for execution.

LAW 5: All operations observable via EventStore.
LAW 13: No direct execution — routing only.
RULE 1: All methods are deterministic.

Ref: Canon LAW 5, LAW 13, RULE 1
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ICognitiveOrchestrator(Protocol):
    """Cognitive orchestration facade.

    plan(task):             Synthesize a plan from an intent.
    critique(plan):         Evaluate plan quality and risk.
    optimize(dag):          Optimize DAG for resource efficiency.
    submit_to_runtime(id):  Submit a validated plan for execution.
    """

    def plan(self, task: Dict[str, Any]) -> str:
        """Synthesize a plan from a task intent.

        Returns a plan_id (str) that identifies the generated plan.
        """
        ...

    def critique(self, plan_id: str) -> Dict[str, Any]:
        """Evaluate a plan and return assessment.

        Returns dict with score, risks, and suggested corrections.
        """
        ...

    def optimize(self, dag: Any) -> Any:
        """Optimize a DAG for resource and cost efficiency.

        Returns the optimized DAG structure.
        """
        ...

    def submit_to_runtime(self, plan_id: str) -> str:
        """Submit a validated plan to UnifiedRuntimeAPI for execution.

        Returns an execution_id (str).
        """
        ...
