"""Phase I2 — Data Trace Correlator.  # LAW-5 LAW-12

Propagates data_trace_id across I1.K8s → I2.PostgreSQL → I2.DistributedLog →
I2.RuntimeAnalytics → F2.ControlPlane → F4.Observability layers, ensuring
every data operation is fully back-traceable.

Ref: Canon LAW 5 (Observability), LAW 12 (Traceability)
Ref: artifacts/design/i2/04_integration_blueprint.md §3
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional


class DataTraceCorrelator:  # LAW-5 LAW-12
    """Manages data_trace_id propagation across data infrastructure layers."""

    _seq: int = 0

    def __init__(self) -> None:
        self._correlations: Dict[str, Dict[str, str]] = {}

    def generate_data_trace_id(self, infra_trace_id: str, operation_type: str) -> str:
        DataTraceCorrelator._seq += 1
        raw = f"{infra_trace_id}:i2:{operation_type}:{time.time_ns()}:{DataTraceCorrelator._seq}"
        return f"data_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    def record_correlation(self, trace_id: str, layer: str, correlated_id: str) -> None:
        if trace_id not in self._correlations:
            self._correlations[trace_id] = {}
        self._correlations[trace_id][layer] = correlated_id

    def propagate_to_postgres(self, data_trace_id: str, tx_id: str) -> Dict[str, str]:
        self.record_correlation(data_trace_id, "i2_postgresql", tx_id)
        return {"data_trace_id": data_trace_id, "tx_id": tx_id, "target_layer": "i2_postgresql"}

    def propagate_to_log(self, data_trace_id: str, entry_id: str) -> Dict[str, str]:
        self.record_correlation(data_trace_id, "i2_distributed_log", entry_id)
        return {"data_trace_id": data_trace_id, "entry_id": entry_id, "target_layer": "i2_distributed_log"}

    def propagate_to_analytics(self, data_trace_id: str, window_id: str) -> Dict[str, str]:
        self.record_correlation(data_trace_id, "i2_analytics", window_id)
        return {"data_trace_id": data_trace_id, "window_id": window_id, "target_layer": "i2_analytics"}

    def propagate_to_migration(self, data_trace_id: str, migration_id: str) -> Dict[str, str]:
        self.record_correlation(data_trace_id, "i2_migration", migration_id)
        return {"data_trace_id": data_trace_id, "migration_id": migration_id, "target_layer": "i2_migration"}

    def propagate_to_f2(self, data_trace_id: str, resource_id: str) -> Dict[str, str]:
        self.record_correlation(data_trace_id, "f2_control_plane", resource_id)
        return {"data_trace_id": data_trace_id, "resource_id": resource_id, "target_layer": "f2_control_plane"}

    def propagate_to_f4(self, data_trace_id: str, span_data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        f4_id = f"f4_{hashlib.sha256(f'{data_trace_id}:f4:{time.time_ns()}'.encode()).hexdigest()[:20]}"
        self.record_correlation(data_trace_id, "f4_observability", f4_id)
        return {"data_trace_id": data_trace_id, "f4_span_id": f4_id, "target_layer": "f4_observability"}

    def propagate_to_i1(self, data_trace_id: str, infra_trace_id: str) -> Dict[str, str]:
        self.record_correlation(data_trace_id, "i1_infra", infra_trace_id)
        return {"data_trace_id": data_trace_id, "infra_trace_id": infra_trace_id, "target_layer": "i1_infra"}

    def correlation_for(self, trace_id: str, layer: str) -> str:
        return self._correlations.get(trace_id, {}).get(layer, "")

    def trace_chain(self, data_trace_id: str) -> Dict[str, Any]:
        for tid, layers in self._correlations.items():
            if tid == data_trace_id:
                return {"data_trace_id": data_trace_id, "layers": dict(layers)}
        return {}

    def resolve_infra_trace_id(self, data_trace_id: str) -> Optional[str]:
        layers = self._correlations.get(data_trace_id, {})
        return layers.get("i1_infra")

    def all_traces(self) -> List[str]:
        return list(self._correlations.keys())

    def reset(self) -> None:
        self._correlations.clear()
