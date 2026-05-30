"""Phase J1 — DevEx Trace Correlator.  # LAW-5 LAW-12

Propagates devex_trace_id across SDK → CLI → Doc Generator → Spec Publisher
layers and into F1 UnifiedRuntime → EventBus → F4 Observability.

Ref: Canon LAW 5 (Observability), LAW 12 (Traceability)
Ref: artifacts/design/j1/04_integration_blueprint.md §3 (Correlation ID Strategy)
Ref: I2 DataTraceCorrelator, I3 RecoveryTraceCorrelator
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional


class DevExTraceCorrelator:  # LAW-5 LAW-12
    """Manages devex_trace_id generation and propagation across DevEx layers.

    LAW 5: Every DevEx operation is observable via trace chain.
    LAW 12: Every trace is fully back-traceable to the originating SDK/CLI call.
    """

    _seq: int = 0

    def __init__(self) -> None:
        self._traces: Dict[str, Dict[str, str]] = {}

    def generate_devex_trace_id(  # LAW-12
        self,
        session_id: str,
        operation_type: str,
    ) -> str:
        DevExTraceCorrelator._seq += 1
        raw = f"{session_id}:{operation_type}:{time.time_ns()}:{DevExTraceCorrelator._seq}"
        return f"dx_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    def record_trace(  # LAW-12
        self,
        devex_trace_id: str,
        layer: str,
        correlated_id: str,
    ) -> None:
        if devex_trace_id not in self._traces:
            self._traces[devex_trace_id] = {}
        self._traces[devex_trace_id][layer] = correlated_id

    def propagate_to_f1(  # LAW-5
        self,
        devex_trace_id: str,
        f1_trace_id: str,
    ) -> Dict[str, str]:
        self.record_trace(devex_trace_id, "f1_unified_api", f1_trace_id)
        return {"devex_trace_id": devex_trace_id, "f1_trace_id": f1_trace_id, "target_layer": "f1_unified_api"}

    def propagate_to_f4(  # LAW-5
        self,
        devex_trace_id: str,
        span_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        f4_id = f"f4_{hashlib.sha256(f'{devex_trace_id}:f4:{time.time_ns()}'.encode()).hexdigest()[:20]}"
        self.record_trace(devex_trace_id, "f4_observability", f4_id)
        return {"devex_trace_id": devex_trace_id, "f4_span_id": f4_id, "target_layer": "f4_observability"}

    def propagate_to_sdk(  # LAW-5
        self,
        devex_trace_id: str,
        sdk_trace_id: str,
    ) -> Dict[str, str]:
        self.record_trace(devex_trace_id, "sdk", sdk_trace_id)
        return {"devex_trace_id": devex_trace_id, "sdk_trace_id": sdk_trace_id, "target_layer": "sdk"}

    def propagate_to_cli(  # LAW-5
        self,
        devex_trace_id: str,
        cli_trace_id: str,
    ) -> Dict[str, str]:
        self.record_trace(devex_trace_id, "cli", cli_trace_id)
        return {"devex_trace_id": devex_trace_id, "cli_trace_id": cli_trace_id, "target_layer": "cli"}

    def propagate_to_doc(  # LAW-5
        self,
        devex_trace_id: str,
        doc_artifact_id: str,
    ) -> Dict[str, str]:
        self.record_trace(devex_trace_id, "doc_generator", doc_artifact_id)
        return {"devex_trace_id": devex_trace_id, "doc_artifact_id": doc_artifact_id, "target_layer": "doc_generator"}

    def propagate_to_spec(  # LAW-5
        self,
        devex_trace_id: str,
        spec_id: str,
    ) -> Dict[str, str]:
        self.record_trace(devex_trace_id, "spec_publisher", spec_id)
        return {"devex_trace_id": devex_trace_id, "spec_id": spec_id, "target_layer": "spec_publisher"}

    def correlation_for(self, trace_id: str, layer: str) -> str:
        return self._traces.get(trace_id, {}).get(layer, "")

    def trace_chain(self, devex_trace_id: str) -> Dict[str, Any]:
        for tid, layers in self._traces.items():
            if tid == devex_trace_id:
                return {"devex_trace_id": devex_trace_id, "layers": dict(layers)}
        return {}

    def all_traces(self) -> List[str]:
        return list(self._traces.keys())

    def reset(self) -> None:
        self._traces.clear()
