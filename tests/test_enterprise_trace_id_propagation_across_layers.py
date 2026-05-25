"""Phase J2 — Enterprise Trace ID Propagation Tests.  # LAW-5 LAW-12 LAW-23 RULE-4

Tests the enterprise_trace_id propagation chain across all J2 layers:
F1 → TenantRouter → UsageMeter → BillingEngine → ComplianceAuditor → F4.

LAW 12: Every operation must carry an enterprise_trace_id that is fully
back-traceable. RULE 4: Propagation rules P-R1–P-R6 ensure integrity.

Ref: artifacts/design/j2/04_integration_blueprint.md §2 (Correlation ID)
Ref: Canon LAW 5 (Observability), LAW 12 (Traceability), RULE 4
"""

from __future__ import annotations

import hashlib

import pytest

from core.enterprise.trace_correlator import EnterpriseTraceCorrelator


SESSION_ID = "sess_test_j2_prop_001"
TENANT_ID = "tenant_acme"


class TestTraceIdGeneration:
    """Enterprise trace ID generation meets format requirements."""

    def test_generates_valid_enterprise_trace_id(self) -> None:
        tc = EnterpriseTraceCorrelator()
        trace_id = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        assert trace_id.startswith("entr_")
        assert len(trace_id) > 30

    def test_generates_unique_ids(self) -> None:
        tc = EnterpriseTraceCorrelator()
        t1 = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        t2 = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        assert t1 != t2

    def test_trace_id_is_non_empty(self) -> None:
        tc = EnterpriseTraceCorrelator()
        trace_id = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        assert len(trace_id) >= 8


class TestTracePropagation:
    """Trace propagates through all J2 layers without loss."""

    def test_propagate_to_f1(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tid = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        r = tc.propagate_to_f1(tid, "f1_trace_001")
        assert r["target_layer"] == "f1_unified_api"
        assert r["enterprise_trace_id"] == tid

    def test_propagate_to_router(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tid = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        r = tc.propagate_to_router(tid, "route_trace_001")
        assert r["target_layer"] == "tenant_router"

    def test_propagate_to_meter(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tid = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        r = tc.propagate_to_meter(tid, "meter_trace_001")
        assert r["target_layer"] == "usage_meter"

    def test_propagate_to_billing(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tid = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        r = tc.propagate_to_billing(tid, "bill_trace_001")
        assert r["target_layer"] == "billing_engine"

    def test_propagate_to_auditor(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tid = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        r = tc.propagate_to_auditor(tid, "audit_trace_001")
        assert r["target_layer"] == "compliance_auditor"

    def test_propagate_to_f4(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tid = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        r = tc.propagate_to_f4(tid)
        assert r["target_layer"] == "f4_observability"
        assert r["f4_span_id"].startswith("f4_")


class TestEndToEndPropagation:
    """Full chain: F1 → Router → Meter → Billing → Auditor → F4."""

    def test_full_chain_f1_to_f4(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tid = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        tc.propagate_to_f1(tid, "f1_001")
        tc.propagate_to_router(tid, "rt_001")
        tc.propagate_to_meter(tid, "mt_001")
        tc.propagate_to_billing(tid, "bl_001")
        tc.propagate_to_auditor(tid, "au_001")
        tc.propagate_to_f4(tid)
        chain = tc.trace_chain(tid)
        assert "f1_unified_api" in chain.get("layers", {})
        assert "tenant_router" in chain.get("layers", {})
        assert "usage_meter" in chain.get("layers", {})
        assert "billing_engine" in chain.get("layers", {})
        assert "compliance_auditor" in chain.get("layers", {})
        assert "f4_observability" in chain.get("layers", {})

    def test_all_traces_recorded(self) -> None:
        tc = EnterpriseTraceCorrelator()
        t1 = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        t2 = tc.generate_enterprise_trace_id(SESSION_ID, "tenant_b")
        tc.propagate_to_f1(t1, "f1_001")
        tc.propagate_to_f1(t2, "f1_002")
        all_traces = tc.all_traces()
        assert t1 in all_traces
        assert t2 in all_traces

    def test_reset_clears_traces(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tid = tc.generate_enterprise_trace_id(SESSION_ID, TENANT_ID)
        tc.propagate_to_f1(tid, "f1_001")
        tc.reset()
        assert len(tc.all_traces()) == 0
