"""Phase G5 — Swarm Trace Correlator.  # LAW-12

Propagates mission_trace_id across G1 → G5 → G2/G3 → F2 layers,
ensuring every swarm mission is back-traceable.

Ref: Canon LAW 12 (Traceability)
Ref: artifacts/design/g5/04_integration_blueprint.md §3
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.multiagent.trace_correlator")


class SwarmTraceCorrelator:  # LAW-12
    """Manages mission_trace_id propagation across layers."""

    def __init__(self) -> None:
        self._correlations: Dict[str, Dict[str, str]] = {}

    def generate_trace_id(
        self, intent_id: str, plan_id: str,
    ) -> str:
        raw = f"{intent_id}:{plan_id}:{time.time_ns()}"
        return f"msn_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    def record_correlation(
        self, plan_id: str, layer: str, mission_trace_id: str,
    ) -> None:
        if plan_id not in self._correlations:
            self._correlations[plan_id] = {}
        self._correlations[plan_id][layer] = mission_trace_id

    def correlation_for(self, plan_id: str, layer: str) -> str:
        return self._correlations.get(plan_id, {}).get(layer, "")

    def propagate_to_g1(self, plan_id: str, mission_trace_id: str) -> Dict[str, str]:
        self.record_correlation(plan_id, "g1_planner", mission_trace_id)
        return {"mission_trace_id": mission_trace_id, "plan_id": plan_id, "target_layer": "g1_planner"}

    def propagate_to_g2(self, plan_id: str, mission_trace_id: str) -> Dict[str, str]:
        self.record_correlation(plan_id, "g2_critic", mission_trace_id)
        return {"mission_trace_id": mission_trace_id, "plan_id": plan_id, "target_layer": "g2_critic"}

    def propagate_to_g3(self, plan_id: str, mission_trace_id: str) -> Dict[str, str]:
        self.record_correlation(plan_id, "g3_optimizer", mission_trace_id)
        return {"mission_trace_id": mission_trace_id, "plan_id": plan_id, "target_layer": "g3_optimizer"}

    def propagate_to_f2(self, plan_id: str, mission_trace_id: str) -> Dict[str, str]:
        self.record_correlation(plan_id, "f2_control", mission_trace_id)
        return {"mission_trace_id": mission_trace_id, "plan_id": plan_id, "target_layer": "f2_control"}

    def trace_chain(self, mission_trace_id: str) -> Dict[str, Any]:
        for plan_id, layers in self._correlations.items():
            for layer, tid in layers.items():
                if tid == mission_trace_id:
                    return {"plan_id": plan_id, "mission_trace_id": mission_trace_id, "layers": dict(layers)}
        return {}

    def resolve_plan_id(self, mission_trace_id: str) -> Optional[str]:
        for plan_id, layers in self._correlations.items():
            if mission_trace_id in layers.values():
                return plan_id
        return None

    def reset(self) -> None:
        self._correlations.clear()
