"""Phase G3 — Trace Correlator.  # LAW-12

Propagates optimizer_trace_id across G3 → G1 → F3 → G2 layers,
ensuring every optimisation proposal is back-traceable.

Ref: Canon LAW 12 (Traceability)
Ref: artifacts/design/g3/04_integration_blueprint.md §2
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from core.runtime.models.optimizer_models import OptimizationProposal

logger = logging.getLogger("emo_ai.optimizer.trace_correlator")


class OptimizerTraceCorrelator:  # LAW-12
    """Manages optimizer_trace_id propagation across layers.

    LAW 12: Every optimisation proposal is traceable via optimizer_trace_id.
    """

    def __init__(self) -> None:
        self._correlations: Dict[str, Dict[str, str]] = {}

    def generate_trace_id(  # LAW-12
        self,
        plan_id: str,
        metrics: Dict[str, Any],
    ) -> str:
        raw = f"{plan_id}:{time.time_ns()}:{hashlib.sha256(str(metrics).encode()).hexdigest()[:12]}"
        return f"opt_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    def correlation_for(  # LAW-12
        self,
        plan_id: str,
        layer: str,
    ) -> str:
        return self._correlations.get(plan_id, {}).get(layer, "")

    def record_correlation(  # LAW-12
        self,
        plan_id: str,
        layer: str,
        optimizer_trace_id: str,
    ) -> None:
        if plan_id not in self._correlations:
            self._correlations[plan_id] = {}
        self._correlations[plan_id][layer] = optimizer_trace_id

    def trace_chain(  # LAW-12
        self,
        optimizer_trace_id: str,
    ) -> Dict[str, str]:
        for plan_id, layers in self._correlations.items():
            for layer, tid in layers.items():
                if tid == optimizer_trace_id:
                    return {
                        "plan_id": plan_id,
                        "optimizer_trace_id": optimizer_trace_id,
                        "layers": dict(layers),
                    }
        return {}

    def propagate_to_g1(  # LAW-12
        self,
        plan_id: str,
        optimizer_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(plan_id, "g1_planner", optimizer_trace_id)
        return {
            "optimizer_trace_id": optimizer_trace_id,
            "plan_id": plan_id,
            "target_layer": "g1_planner",
        }

    def propagate_to_f3(  # LAW-12
        self,
        plan_id: str,
        optimizer_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(plan_id, "f3_scheduler", optimizer_trace_id)
        return {
            "optimizer_trace_id": optimizer_trace_id,
            "plan_id": plan_id,
            "target_layer": "f3_scheduler",
        }

    def propagate_to_g2(  # LAW-12
        self,
        plan_id: str,
        optimizer_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(plan_id, "g2_critic", optimizer_trace_id)
        return {
            "optimizer_trace_id": optimizer_trace_id,
            "plan_id": plan_id,
            "target_layer": "g2_critic",
        }

    def resolve_plan_id(  # LAW-12
        self,
        optimizer_trace_id: str,
    ) -> Optional[str]:
        for plan_id, layers in self._correlations.items():
            if optimizer_trace_id in layers.values():
                return plan_id
        return None

    def reset(self) -> None:
        self._correlations.clear()
