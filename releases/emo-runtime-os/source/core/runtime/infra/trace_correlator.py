"""Phase I1 — Infra Trace Correlator.  # LAW-5 LAW-12

Propagates infra_trace_id across F2.ControlPlane → I1.Queue → I1.K8s →
F4.Observability layers, ensuring every infrastructure operation is fully
back-traceable.

Ref: Canon LAW 5 (Observability), LAW 12 (Traceability)
Ref: artifacts/design/i1/04_integration_blueprint.md §3
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional


class InfraTraceCorrelator:  # LAW-5 LAW-12
    """Manages infra_trace_id propagation across infrastructure layers.

    LAW 5: Every infrastructure operation carries an infra_trace_id.
    LAW 12: Every trace is fully back-traceable to the originating mission.
    """

    _seq: int = 0

    def __init__(self) -> None:
        self._correlations: Dict[str, Dict[str, str]] = {}  # trace_id -> {layer -> correlated_id}

    def generate_infra_trace_id(  # LAW-12
        self,
        mission_trace_id: str,
        operation_type: str,
    ) -> str:
        InfraTraceCorrelator._seq += 1
        raw = f"{mission_trace_id}:i1:{operation_type}:{time.time_ns()}:{InfraTraceCorrelator._seq}"
        return f"infra_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    def record_correlation(  # LAW-12
        self,
        trace_id: str,
        layer: str,
        correlated_id: str,
    ) -> None:
        if trace_id not in self._correlations:
            self._correlations[trace_id] = {}
        self._correlations[trace_id][layer] = correlated_id

    def propagate_to_f2(  # LAW-5
        self,
        infra_trace_id: str,
        deployment_id: str,
        cluster_id: str = "",
    ) -> Dict[str, str]:
        self.record_correlation(infra_trace_id, "f2_control_plane", deployment_id)
        return {
            "infra_trace_id": infra_trace_id,
            "deployment_id": deployment_id,
            "target_layer": "f2_control_plane",
        }

    def propagate_to_f4(  # LAW-5
        self,
        infra_trace_id: str,
        span_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        f4_id = f"f4_{hashlib.sha256(f'{infra_trace_id}:f4:{time.time_ns()}'.encode()).hexdigest()[:20]}"
        self.record_correlation(infra_trace_id, "f4_observability", f4_id)
        return {
            "infra_trace_id": infra_trace_id,
            "f4_span_id": f4_id,
            "target_layer": "f4_observability",
        }

    def propagate_to_queue(  # LAW-5
        self,
        infra_trace_id: str,
        msg_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(infra_trace_id, "i1_queue", msg_id)
        return {
            "infra_trace_id": infra_trace_id,
            "msg_id": msg_id,
            "target_layer": "i1_queue",
        }

    def propagate_to_k8s(  # LAW-5
        self,
        infra_trace_id: str,
        deployment_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(infra_trace_id, "i1_k8s", deployment_id)
        return {
            "infra_trace_id": infra_trace_id,
            "deployment_id": deployment_id,
            "target_layer": "i1_k8s",
        }

    def propagate_to_ha(  # LAW-5
        self,
        infra_trace_id: str,
        cluster_id: str,
        term: int = 0,
    ) -> Dict[str, str]:
        ha_id = f"ha_{cluster_id}_t{term}"
        self.record_correlation(infra_trace_id, "i1_ha", ha_id)
        return {
            "infra_trace_id": infra_trace_id,
            "ha_id": ha_id,
            "target_layer": "i1_ha",
        }

    def propagate_to_storage(  # LAW-5
        self,
        infra_trace_id: str,
        uri: str,
    ) -> Dict[str, str]:
        self.record_correlation(infra_trace_id, "i1_storage", uri)
        return {
            "infra_trace_id": infra_trace_id,
            "uri": uri,
            "target_layer": "i1_storage",
        }

    def correlation_for(self, trace_id: str, layer: str) -> str:
        return self._correlations.get(trace_id, {}).get(layer, "")

    def trace_chain(self, infra_trace_id: str) -> Dict[str, Any]:
        for tid, layers in self._correlations.items():
            if tid == infra_trace_id:
                return {
                    "infra_trace_id": infra_trace_id,
                    "layers": dict(layers),
                }
        return {}

    def resolve_mission_trace_id(self, infra_trace_id: str) -> Optional[str]:
        for tid in self._correlations:
            if tid == infra_trace_id:
                return tid.split(":")[0] if ":" in tid else None
        return None

    def all_traces(self) -> List[str]:
        return list(self._correlations.keys())

    def reset(self) -> None:
        self._correlations.clear()
