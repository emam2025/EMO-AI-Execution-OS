"""Phase G4 — Trace Correlator.  # LAW-12

Propagates synthesis_trace_id across G1 → G4 → Phase4 Sandbox →
ToolRegistry layers, ensuring every synthesised tool is back-traceable.

Ref: Canon LAW 12 (Traceability)
Ref: artifacts/design/g4/04_integration_blueprint.md §3
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.synthesis.trace_correlator")


class SynthesisTraceCorrelator:  # LAW-12
    """Manages synthesis_trace_id propagation across layers.

    LAW 12: Every synthesised tool is traceable via synthesis_trace_id.
    """

    def __init__(self) -> None:
        self._correlations: Dict[str, Dict[str, str]] = {}

    def generate_trace_id(  # LAW-12
        self,
        intent_id: str,
        plan_id: str,
    ) -> str:
        raw = f"{intent_id}:{plan_id}:{time.time_ns()}"
        return f"syn_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    def record_correlation(  # LAW-12
        self,
        plan_id: str,
        layer: str,
        synthesis_trace_id: str,
    ) -> None:
        if plan_id not in self._correlations:
            self._correlations[plan_id] = {}
        self._correlations[plan_id][layer] = synthesis_trace_id

    def correlation_for(  # LAW-12
        self,
        plan_id: str,
        layer: str,
    ) -> str:
        return self._correlations.get(plan_id, {}).get(layer, "")

    def propagate_to_g1(  # LAW-12
        self,
        plan_id: str,
        synthesis_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(plan_id, "g1_planner", synthesis_trace_id)
        return {
            "synthesis_trace_id": synthesis_trace_id,
            "plan_id": plan_id,
            "target_layer": "g1_planner",
        }

    def propagate_to_sandbox(  # LAW-12
        self,
        plan_id: str,
        synthesis_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(plan_id, "phase4_sandbox", synthesis_trace_id)
        return {
            "synthesis_trace_id": synthesis_trace_id,
            "plan_id": plan_id,
            "target_layer": "phase4_sandbox",
        }

    def propagate_to_registry(  # LAW-12
        self,
        plan_id: str,
        synthesis_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(plan_id, "tool_registry", synthesis_trace_id)
        return {
            "synthesis_trace_id": synthesis_trace_id,
            "plan_id": plan_id,
            "target_layer": "tool_registry",
        }

    def trace_chain(  # LAW-12
        self,
        synthesis_trace_id: str,
    ) -> Dict[str, Any]:
        for plan_id, layers in self._correlations.items():
            for layer, tid in layers.items():
                if tid == synthesis_trace_id:
                    return {
                        "plan_id": plan_id,
                        "synthesis_trace_id": synthesis_trace_id,
                        "layers": dict(layers),
                    }
        return {}

    def resolve_plan_id(  # LAW-12
        self,
        synthesis_trace_id: str,
    ) -> Optional[str]:
        for plan_id, layers in self._correlations.items():
            if synthesis_trace_id in layers.values():
                return plan_id
        return None

    def reset(self) -> None:
        self._correlations.clear()
