"""Phase G2 — Trace Correlator.  # LAW-12

Propagates critic_trace_id across G2 → F4 → G1 → D9 layers,
ensuring every diagnosis and correction is back-traceable.

Ref: Canon LAW 12 (Traceability)
Ref: artifacts/design/g2/04_integration_blueprint.md §2
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from core.runtime.models.critic_models import DiagnosisReport

logger = logging.getLogger("emo_ai.critic.trace_correlator")


class CriticTraceCorrelator:  # LAW-12
    """Manages critic_trace_id propagation across layers.

    Each diagnosis gets a unique critic_trace_id that is forwarded
    through corrections to G1, D9, and F4 for complete traceability.

    LAW 12: Every diagnosis and correction is traceable via critic_trace_id.
    """

    def __init__(self) -> None:
        self._correlations: Dict[str, Dict[str, str]] = {}

    def generate_trace_id(  # LAW-12
        self,
        plan_id: str,
        trace: Dict[str, Any],
    ) -> str:
        raw = f"{plan_id}:{time.time_ns()}:{hashlib.sha256(str(trace).encode()).hexdigest()[:12]}"
        return f"critic_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    def correlation_for(  # LAW-12
        self,
        plan_id: str,
        layer: str,
    ) -> str:
        correlations = self._correlations.get(plan_id, {})
        return correlations.get(layer, "")

    def record_correlation(  # LAW-12
        self,
        plan_id: str,
        layer: str,
        critic_trace_id: str,
    ) -> None:
        if plan_id not in self._correlations:
            self._correlations[plan_id] = {}
        self._correlations[plan_id][layer] = critic_trace_id
        logger.debug("Recorded %s → %s = %s", plan_id, layer, critic_trace_id)

    def trace_chain(  # LAW-12
        self,
        critic_trace_id: str,
    ) -> Dict[str, str]:
        for plan_id, layers in self._correlations.items():
            for layer, tid in layers.items():
                if tid == critic_trace_id:
                    return {
                        "plan_id": plan_id,
                        "critic_trace_id": critic_trace_id,
                        "layers": dict(layers),
                    }
        return {}

    def propagate_to_g1(  # LAW-12
        self,
        plan_id: str,
        critic_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(plan_id, "g2_critic", critic_trace_id)
        return {
            "critic_trace_id": critic_trace_id,
            "plan_id": plan_id,
            "target_layer": "g1_planner",
        }

    def propagate_to_d9(  # LAW-12
        self,
        plan_id: str,
        critic_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(plan_id, "d9_feedback", critic_trace_id)
        return {
            "critic_trace_id": critic_trace_id,
            "plan_id": plan_id,
            "target_layer": "d9_feedback",
        }

    def propagate_to_f4(  # LAW-12
        self,
        plan_id: str,
        critic_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(plan_id, "f4_observability", critic_trace_id)
        return {
            "critic_trace_id": critic_trace_id,
            "plan_id": plan_id,
            "target_layer": "f4_observability",
        }

    def resolve_plan_id(  # LAW-12
        self,
        critic_trace_id: str,
    ) -> Optional[str]:
        for plan_id, layers in self._correlations.items():
            if critic_trace_id in layers.values():
                return plan_id
        return None

    def reset(self) -> None:
        self._correlations.clear()
