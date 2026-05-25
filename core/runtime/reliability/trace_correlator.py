"""Phase I3 — Recovery Trace Correlator.  # LAW-5 LAW-8 LAW-12

Propagates recovery_trace_id across I2.Data → I3.Reliability → I1.Infra →
F2.ControlPlane → F4.Observability layers, ensuring every reliability
operation is fully back-traceable.

Ref: Canon LAW 5 (Observability), LAW 8 (Recoverability), LAW 12 (Traceability)
Ref: artifacts/design/i3/04_integration_blueprint.md §3
Ref: I1 InfraTraceCorrelator, I2 DataTraceCorrelator
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional


class RecoveryTraceCorrelator:  # LAW-5 LAW-8 LAW-12
    """Manages recovery_trace_id propagation across reliability layers.

    LAW 5: Every reliability operation carries a recovery_trace_id.
    LAW 8: Every trace is fully back-traceable for recoverability.
    LAW 12: Every trace is fully back-traceable to the originating data operation.
    """

    _seq: int = 0

    def __init__(self) -> None:
        self._correlations: Dict[str, Dict[str, str]] = {}

    def generate_recovery_trace_id(  # LAW-12
        self,
        data_trace_id: str,
        operation_type: str,
    ) -> str:
        RecoveryTraceCorrelator._seq += 1
        raw = f"{data_trace_id}:i3:{operation_type}:{time.time_ns()}:{RecoveryTraceCorrelator._seq}"
        return f"rec_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    def record_correlation(  # LAW-12
        self,
        trace_id: str,
        layer: str,
        correlated_id: str,
    ) -> None:
        if trace_id not in self._correlations:
            self._correlations[trace_id] = {}
        self._correlations[trace_id][layer] = correlated_id

    def propagate_to_failover(  # LAW-5
        self,
        recovery_trace_id: str,
        failover_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(recovery_trace_id, "i3_failover", failover_id)
        return {
            "recovery_trace_id": recovery_trace_id,
            "failover_id": failover_id,
            "target_layer": "i3_failover",
        }

    def propagate_to_dr(  # LAW-5
        self,
        recovery_trace_id: str,
        recovery_point_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(recovery_trace_id, "i3_disaster_recovery", recovery_point_id)
        return {
            "recovery_trace_id": recovery_trace_id,
            "recovery_point_id": recovery_point_id,
            "target_layer": "i3_disaster_recovery",
        }

    def propagate_to_rolling_update(  # LAW-5
        self,
        recovery_trace_id: str,
        deployment_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(recovery_trace_id, "i3_rolling_update", deployment_id)
        return {
            "recovery_trace_id": recovery_trace_id,
            "deployment_id": deployment_id,
            "target_layer": "i3_rolling_update",
        }

    def propagate_to_migration(  # LAW-5
        self,
        recovery_trace_id: str,
        migration_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(recovery_trace_id, "i3_migration", migration_id)
        return {
            "recovery_trace_id": recovery_trace_id,
            "migration_id": migration_id,
            "target_layer": "i3_migration",
        }

    def propagate_to_i1(  # LAW-5
        self,
        recovery_trace_id: str,
        infra_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(recovery_trace_id, "i1_infra", infra_trace_id)
        return {
            "recovery_trace_id": recovery_trace_id,
            "infra_trace_id": infra_trace_id,
            "target_layer": "i1_infra",
        }

    def propagate_to_i2(  # LAW-5
        self,
        recovery_trace_id: str,
        data_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(recovery_trace_id, "i2_data", data_trace_id)
        return {
            "recovery_trace_id": recovery_trace_id,
            "data_trace_id": data_trace_id,
            "target_layer": "i2_data",
        }

    def propagate_to_f2(  # LAW-5
        self,
        recovery_trace_id: str,
        resource_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(recovery_trace_id, "f2_control_plane", resource_id)
        return {
            "recovery_trace_id": recovery_trace_id,
            "resource_id": resource_id,
            "target_layer": "f2_control_plane",
        }

    def propagate_to_f4(  # LAW-5
        self,
        recovery_trace_id: str,
        span_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        f4_id = f"f4_{hashlib.sha256(f'{recovery_trace_id}:f4:{time.time_ns()}'.encode()).hexdigest()[:20]}"
        self.record_correlation(recovery_trace_id, "f4_observability", f4_id)
        return {
            "recovery_trace_id": recovery_trace_id,
            "f4_span_id": f4_id,
            "target_layer": "f4_observability",
        }

    def correlation_for(self, trace_id: str, layer: str) -> str:
        return self._correlations.get(trace_id, {}).get(layer, "")

    def trace_chain(self, recovery_trace_id: str) -> Dict[str, Any]:
        for tid, layers in self._correlations.items():
            if tid == recovery_trace_id:
                return {
                    "recovery_trace_id": recovery_trace_id,
                    "layers": dict(layers),
                }
        return {}

    def resolve_data_trace_id(self, recovery_trace_id: str) -> Optional[str]:
        layers = self._correlations.get(recovery_trace_id, {})
        return layers.get("i2_data")

    def all_traces(self) -> List[str]:
        return list(self._correlations.keys())

    def reset(self) -> None:
        self._correlations.clear()
