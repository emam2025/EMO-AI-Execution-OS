"""Phase J3 — Readiness Trace Correlator.  # LAW-5 LAW-8 LAW-12 RULE-4

Propagates readiness_trace_id across J3 ChaosInjector → LoadOrchestrator →
StabilityValidator → CertificationGate → I1/I2/F4 Observability.

LAW 8: Every chaos/recovery operation carries back-traceable readiness_trace_id.
LAW 12: Every trace is fully back-traceable from F4 to the originating injection.
RULE 4: All trace propagation MUST preserve the full chain.

Ref: artifacts/design/j3/04_integration_blueprint.md §2 (Correlation ID Strategy)
Ref: Canon LAW 5 (Observability), LAW 8 (Recoverability), LAW 12 (Traceability)
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional


class ReadinessTraceCorrelator:  # LAW-5 LAW-8 LAW-12 RULE-4
    """Manages readiness_trace_id generation and propagation across J3 layers.

    LAW 5: Every readiness operation is observable via trace chain.
    LAW 8: Every trace is fully back-traceable from F4 to the originating
           chaos injection or load test trigger.
    LAW 12: Trace chains are preserved end-to-end.
    RULE 4: Propagation rules P-R1–P-R6 ensure chain integrity.
    """

    def __init__(self) -> None:
        self._traces: Dict[str, Dict[str, str]] = {}

    def generate_readiness_trace_id(  # LAW-8 LAW-12 RULE-2
        self,
        session_id: str,
        scenario_id: str,
    ) -> str:
        raw = f"{session_id}:{scenario_id}:{time.time_ns()}"
        return f"rdns_{hashlib.sha256(raw.encode()).hexdigest()[:28]}"

    def record_trace(  # LAW-12
        self,
        readiness_trace_id: str,
        layer: str,
        correlated_id: str,
    ) -> None:
        if readiness_trace_id not in self._traces:
            self._traces[readiness_trace_id] = {}
        self._traces[readiness_trace_id][layer] = correlated_id

    def propagate_to_chaos(  # LAW-5
        self,
        readiness_trace_id: str,
        injection_id: str,
    ) -> Dict[str, str]:
        self.record_trace(readiness_trace_id, "chaos_injector", injection_id)
        return {"readiness_trace_id": readiness_trace_id, "injection_id": injection_id, "target_layer": "chaos_injector"}

    def propagate_to_load(  # LAW-5
        self,
        readiness_trace_id: str,
        profile_id: str,
    ) -> Dict[str, str]:
        self.record_trace(readiness_trace_id, "load_orchestrator", profile_id)
        return {"readiness_trace_id": readiness_trace_id, "profile_id": profile_id, "target_layer": "load_orchestrator"}

    def propagate_to_stability(  # LAW-5
        self,
        readiness_trace_id: str,
        metric_id: str,
    ) -> Dict[str, str]:
        self.record_trace(readiness_trace_id, "stability_validator", metric_id)
        return {"readiness_trace_id": readiness_trace_id, "metric_id": metric_id, "target_layer": "stability_validator"}

    def propagate_to_certification(  # LAW-5
        self,
        readiness_trace_id: str,
        report_id: str,
    ) -> Dict[str, str]:
        self.record_trace(readiness_trace_id, "certification_gate", report_id)
        return {"readiness_trace_id": readiness_trace_id, "report_id": report_id, "target_layer": "certification_gate"}

    def propagate_to_f4(  # LAW-5
        self,
        readiness_trace_id: str,
        span_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        f4_id = f"f4_{hashlib.sha256(f'{readiness_trace_id}:f4:{time.time_ns()}'.encode()).hexdigest()[:20]}"
        self.record_trace(readiness_trace_id, "f4_observability", f4_id)
        return {"readiness_trace_id": readiness_trace_id, "f4_span_id": f4_id, "target_layer": "f4_observability"}

    def correlation_for(self, trace_id: str, layer: str) -> str:
        return self._traces.get(trace_id, {}).get(layer, "")

    def trace_chain(self, readiness_trace_id: str) -> Dict[str, Any]:
        for tid, layers in self._traces.items():
            if tid == readiness_trace_id:
                return {"readiness_trace_id": readiness_trace_id, "layers": dict(layers)}
        return {}

    def all_traces(self) -> List[str]:
        return list(self._traces.keys())

    def reset(self) -> None:
        self._traces.clear()
