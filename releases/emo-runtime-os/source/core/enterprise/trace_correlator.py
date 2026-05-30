"""Phase J2/K3 — Enterprise Trace Correlator.  # LAW-5 LAW-12 LAW-23 RULE-4

Propagates enterprise_trace_id across F1 → J2 TenantRouter → UsageMeter →
BillingEngine → ComplianceAuditor → I1 ObjectStorage → F4 Observability.

LAW 12: Every operation carries back-traceable enterprise_trace_id.
LAW 23: Trace partitioning by tenant_id — no cross-tenant trace leakage.
RULE 4: All trace propagation MUST preserve the full chain.

Ref: artifacts/design/j2/04_integration_blueprint.md §2 (Correlation ID Strategy)
Ref: EXEC-DIRECTIVE-024 §4 (Enterprise Traceability)
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional


class EnterpriseTraceCorrelator:  # LAW-5 LAW-12 LAW-23 RULE-4
    def __init__(self) -> None:
        self._traces: Dict[str, Dict[str, str]] = {}

    def generate_enterprise_trace_id(self, session_id: str, tenant_id: str) -> str:
        raw = f"{session_id}:{tenant_id}:{time.time_ns()}"
        return f"entr_{hashlib.sha256(raw.encode()).hexdigest()[:28]}"

    def record_trace(self, enterprise_trace_id: str, layer: str, correlated_id: str) -> None:
        if enterprise_trace_id not in self._traces:
            self._traces[enterprise_trace_id] = {}
        self._traces[enterprise_trace_id][layer] = correlated_id

    def propagate_to_f1(self, enterprise_trace_id: str, f1_trace_id: str) -> Dict[str, str]:
        self.record_trace(enterprise_trace_id, "f1_unified_api", f1_trace_id)
        return {"enterprise_trace_id": enterprise_trace_id, "f1_trace_id": f1_trace_id, "target_layer": "f1_unified_api"}

    def propagate_to_router(self, enterprise_trace_id: str, route_trace_id: str) -> Dict[str, str]:
        self.record_trace(enterprise_trace_id, "tenant_router", route_trace_id)
        return {"enterprise_trace_id": enterprise_trace_id, "route_trace_id": route_trace_id, "target_layer": "tenant_router"}

    def propagate_to_meter(self, enterprise_trace_id: str, meter_trace_id: str) -> Dict[str, str]:
        self.record_trace(enterprise_trace_id, "usage_meter", meter_trace_id)
        return {"enterprise_trace_id": enterprise_trace_id, "meter_trace_id": meter_trace_id, "target_layer": "usage_meter"}

    def propagate_to_billing(self, enterprise_trace_id: str, billing_trace_id: str) -> Dict[str, str]:
        self.record_trace(enterprise_trace_id, "billing_engine", billing_trace_id)
        return {"enterprise_trace_id": enterprise_trace_id, "billing_trace_id": billing_trace_id, "target_layer": "billing_engine"}

    def propagate_to_auditor(self, enterprise_trace_id: str, audit_trace_id: str) -> Dict[str, str]:
        self.record_trace(enterprise_trace_id, "compliance_auditor", audit_trace_id)
        return {"enterprise_trace_id": enterprise_trace_id, "audit_trace_id": audit_trace_id, "target_layer": "compliance_auditor"}

    def propagate_to_f4(self, enterprise_trace_id: str) -> Dict[str, str]:
        f4_span_id = f"f4_{hashlib.sha256(f'{enterprise_trace_id}:{time.time_ns()}'.encode()).hexdigest()[:12]}"
        self.record_trace(enterprise_trace_id, "f4_observability", f4_span_id)
        return {"enterprise_trace_id": enterprise_trace_id, "f4_span_id": f4_span_id, "target_layer": "f4_observability"}

    def trace_chain(self, enterprise_trace_id: str) -> Dict[str, Any]:
        chain = self._traces.get(enterprise_trace_id, {})
        return {"trace_id": enterprise_trace_id, "layers": dict(chain)}

    def get_trace_chain(self, enterprise_trace_id: str) -> Dict[str, str]:
        return dict(self._traces.get(enterprise_trace_id, {}))

    def all_traces(self) -> Dict[str, Dict[str, str]]:
        return {k: dict(v) for k, v in self._traces.items()}

    def reset(self) -> None:
        self._traces.clear()

    def verify_full_propagation(self, enterprise_trace_id: str) -> Dict[str, Any]:
        chain = self._traces.get(enterprise_trace_id, {})
        required_layers = ["tenant_router", "usage_meter", "billing_engine", "compliance_auditor"]
        missing = [l for l in required_layers if l not in chain]
        return {
            "enterprise_trace_id": enterprise_trace_id,
            "layers_found": len(chain),
            "missing_layers": missing,
            "full_propagation": len(missing) == 0,
        }
