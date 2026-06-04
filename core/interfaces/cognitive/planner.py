"""Phase G — IPlanner Protocol.

DAG synthesis and plan validation.

LAW 8: All plans governed by critic evaluation.
LAW 13: Constructed via CompositionRoot only.
RULE 1: Planning is deterministic — same intent → same plan.

Ref: Canon LAW 8, LAW 13, RULE 1
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IPlanner(Protocol):
    """Plan synthesis and validation.

    synthesize_dag(intent, constraints):  Build an executable DAG.
    validate_plan(plan_id):               Check plan against constraints.
    """

    def synthesize_dag(
        self,
        intent: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Synthesize an executable DAG from intent.

        Returns a plan_id (str).
        """
        ...

    def validate_plan(self, plan_id: str) -> bool:
        """Validate plan against resource and policy constraints.

        Returns True if the plan is valid.
        """
        ...
