"""Phase G1 — TraceCorrelator implementation.  # LAW-12 # RULE-1

Propagates plan_trace_id across all layers:
  F1.submit() → G1.synthesize() → D8.dispatch() → F4.trace()

Ensures every layer receives the same correlation_id and no
trace information is lost between subsystems.

Ref: Canon LAW 12 (Traceability), RULE 1 (Determinism)
Ref: artifacts/design/g1/04_integration_blueprint.md §2
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.runtime.models.planning_models import ExecutionPlan

logger = logging.getLogger("emo_ai.orchestration.correlator")


class TraceCorrelator:  # LAW-12
    """Manages correlation_id propagation across layers.

    Each layer's correlation is derived from the plan_trace_id and
    tracked per (layer, plan_trace_id) pair for back-tracing.

    LAW 12: Every plan transaction is traceable via correlation_id.
    """

    def __init__(self) -> None:
        self._correlations: Dict[str, Dict[str, str]] = {}

    # ── correlation_for ─────────────────────────────────────────

    def correlation_for(  # LAW-12
        self,
        plan: ExecutionPlan,
        layer: str,
    ) -> str:
        if layer == "g1_planner":
            return f"plan:{plan.plan_id}:v{plan.version}"
        elif layer == "f1_api":
            exec_id = plan.metadata.get("execution_id", "")
            return f"exec:{exec_id}:{plan.plan_trace_id}" if exec_id else plan.plan_trace_id
        elif layer == "d8_mesh":
            return f"d8:{plan.plan_trace_id}"
        elif layer == "f4_observer":
            return f"trace:{plan.plan_trace_id}"
        return plan.plan_trace_id

    # ── record_correlation ──────────────────────────────────────

    def record_correlation(  # LAW-12
        self,
        plan_id: str,
        layer: str,
        correlation_id: str,
    ) -> None:
        if plan_id not in self._correlations:
            self._correlations[plan_id] = {}
        self._correlations[plan_id][layer] = correlation_id
        logger.debug("Recorded %s → %s = %s", plan_id, layer, correlation_id)

    # ── trace_chain ─────────────────────────────────────────────

    def trace_chain(  # LAW-12
        self,
        plan_id: str,
    ) -> Dict[str, str]:
        return dict(self._correlations.get(plan_id, {}))

    # ── resolve_from_f1_execution_id ────────────────────────────

    def resolve_from_f1_execution_id(  # LAW-12
        self,
        execution_id: str,
    ) -> Optional[str]:
        for plan_id, layers in self._correlations.items():
            if any(execution_id in v for v in layers.values()):
                return plan_id
        return None

    # ── propagate_context ───────────────────────────────────────

    def propagate_context(  # LAW-12
        self,
        plan: ExecutionPlan,
        target_layer: str,
    ) -> Dict[str, str]:
        correlation = self.correlation_for(plan, target_layer)
        self.record_correlation(plan.plan_id, target_layer, correlation)

        return {
            "plan_trace_id": plan.plan_trace_id,
            "plan_id": plan.plan_id,
            "version": str(plan.version),
            "correlation_id": correlation,
            "target_layer": target_layer,
        }

    def reset(self) -> None:
        self._correlations.clear()
