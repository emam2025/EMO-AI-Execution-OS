"""Phase J2 — Enterprise Readiness Integration Tests.  # LAW-1 LAW-9 LAW-11 LAW-12 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

5 test groups covering ITenantRouter, IUsageMeter, IBillingEngine,
IComplianceAuditor, and event bus propagation.

Ref: artifacts/design/j2/protocols/01_enterprise_protocols.py
Ref: artifacts/design/j2/03_tenant_isolation_machine.md
Ref: Canon LAW 1, 2, 9, 11, 23-27, RULE 1-5
"""

from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal

import pytest

from core.enterprise.tenant_router import TenantRouter
from core.enterprise.usage_meter import UsageMeter
from core.enterprise.billing_engine import BillingEngine
from core.enterprise.compliance_auditor import ComplianceAuditor
from core.enterprise.isolation_state_machine import IsolationStateMachine
from core.enterprise.trace_correlator import EnterpriseTraceCorrelator


TRACE_ID = "entr_test_integration_001"


# ── Helpers ────────────────────────────────────────────────────


class InMemoryEventBus:
    """Simple in-memory event bus for testing event propagation."""

    def __init__(self) -> None:
        self._events: dict = {}

    def publish(self, topic: str, event: Any) -> None:
        if topic not in self._events:
            self._events[topic] = []
        self._events[topic].append(event)

    def get_events(self, topic: str) -> list:
        return self._events.get(topic, [])


# ── TestLeakageGuardEnforcement (5 tests) ──────────────────────


class TestLeakageGuardEnforcement:
    """G-L1: TenantRouter blocks cross-tenant without scope_verified + policy check."""

    def test_route_request_allows_same_tenant(self) -> None:
        router = TenantRouter()
        router.register_tenant("t1", "strict")
        result = asyncio.run(router.route_request("t1", {"target_tenant": "t1"}, TRACE_ID))
        assert result["routed"] is True

    def test_route_request_blocks_cross_tenant_strict(self) -> None:
        router = TenantRouter()
        router.register_tenant("t1", "strict")
        router.register_tenant("t2", "strict")
        result = asyncio.run(router.route_request("t1", {
            "target_tenant": "t2", "shared_resource_flag": False, "scope_verified": False,
        }, TRACE_ID))
        assert result["routed"] is False

    def test_route_request_allows_cross_tenant_shared_with_verification(self) -> None:
        router = TenantRouter()
        router.register_tenant("t1", "strict")
        router.register_tenant("t2", "shared")
        result = asyncio.run(router.route_request("t1", {
            "target_tenant": "t2", "shared_resource_flag": True, "scope_verified": True,
        }, TRACE_ID))
        assert result["routed"] is True

    def test_validate_tenant_scope_allows_same_tenant(self) -> None:
        router = TenantRouter()
        router.register_tenant("t1", "strict")
        result = asyncio.run(router.validate_tenant_scope("t1", "t1", False, False, TRACE_ID))
        assert result["allowed"] is True

    def test_validate_tenant_scope_blocks_cross_tenant_without_verification(self) -> None:
        router = TenantRouter()
        router.register_tenant("t1", "strict")
        router.register_tenant("t2", "strict")
        result = asyncio.run(router.validate_tenant_scope("t1", "t2", False, False, TRACE_ID))
        assert result["allowed"] is False


# ── TestBillingDeterminism (4 tests) ────────────────────────────


class TestBillingDeterminism:
    """IBillingEngine: same inputs produce same results (RULE 1)."""

    def test_same_tier_same_usage_same_result(self) -> None:
        e1 = BillingEngine()
        e2 = BillingEngine()
        usage = {"dag_execution": "100", "api_call": "500"}
        r1 = asyncio.run(e1.apply_pricing_tier("t1", "professional", usage, TRACE_ID))
        r2 = asyncio.run(e2.apply_pricing_tier("t1", "professional", usage, TRACE_ID))
        assert r1["total"] == r2["total"]
        assert r1["line_items"] == r2["line_items"]

    def test_different_tier_different_cost(self) -> None:
        engine = BillingEngine()
        usage = {"dag_execution": "100"}
        free_r = asyncio.run(engine.apply_pricing_tier("t1", "free", usage, TRACE_ID))
        ent_r = asyncio.run(engine.apply_pricing_tier("t1", "enterprise", usage, TRACE_ID))
        assert free_r["total"] != ent_r["total"]

    def test_generate_invoice_rejects_negative_amount(self) -> None:
        engine = BillingEngine()
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        result = asyncio.run(engine.generate_invoice(
            "t1", period[0], period[1], [], Decimal("-50"), TRACE_ID,
        ))
        assert result.get("error") == "Negative invoice amount"

    def test_payment_state_transition_valid(self) -> None:
        engine = BillingEngine()
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        inv = asyncio.run(engine.generate_invoice(
            "t1", period[0], period[1],
            [{"operation_type": "dag_execution", "units": "100", "rate": "0.005", "subtotal": "0.50"}],
            Decimal("0.50"), TRACE_ID,
        ))
        r = asyncio.run(engine.process_payment_state(inv["invoice_id"], "t1", "processing", TRACE_ID))
        assert r["allowed"] is True
        assert r["to_state"] == "processing"


# ── TestTraceCorrelation (4 tests) ─────────────────────────────


class TestTraceCorrelation:
    """Enterprise trace_id propagates end-to-end without loss."""

    def test_router_records_trace(self) -> None:
        tc = EnterpriseTraceCorrelator()
        router = TenantRouter(trace_correlator=tc)
        router.register_tenant("t1", "strict")
        tid = tc.generate_enterprise_trace_id("sess", "t1")
        asyncio.run(router.route_request("t1", {}, tid))
        chain = tc.trace_chain(tid)
        assert "tenant_router" in chain.get("layers", {})

    def test_meter_records_trace(self) -> None:
        tc = EnterpriseTraceCorrelator()
        meter = UsageMeter(trace_correlator=tc)
        tid = tc.generate_enterprise_trace_id("sess", "t1")
        asyncio.run(meter.record_operation("t1", "dag_execution", Decimal("10"), tid))
        chain = tc.trace_chain(tid)
        assert "usage_meter" in chain.get("layers", {})

    def test_billing_records_trace(self) -> None:
        tc = EnterpriseTraceCorrelator()
        engine = BillingEngine(trace_correlator=tc)
        tid = tc.generate_enterprise_trace_id("sess", "t1")
        asyncio.run(engine.apply_pricing_tier("t1", "professional", {"dag_execution": "100"}, tid))
        chain = tc.trace_chain(tid)
        assert "billing_engine" in chain.get("layers", {})

    def test_auditor_records_trace(self) -> None:
        tc = EnterpriseTraceCorrelator()
        auditor = ComplianceAuditor(trace_correlator=tc)
        tid = tc.generate_enterprise_trace_id("sess", "t1")
        asyncio.run(auditor.collect_audit_trail("t1", "run", "alice", "dag_1", tid))
        chain = tc.trace_chain(tid)
        assert "compliance_auditor" in chain.get("layers", {})


# ── TestComplianceValidationSafety (4 tests) ───────────────────


class TestComplianceValidationSafety:
    """IComplianceAuditor validates entries and blocks on violations."""

    def test_valid_entries_pass_validation(self) -> None:
        auditor = ComplianceAuditor()
        entries = [
            {
                "entry_id": "e1", "tenant_id": "t1", "action": "run",
                "actor": "alice", "target_resource": "dag_1",
                "compliance_hash": IsolationStateMachine.compute_audit_hash(
                    "t1", "run", "alice", "dag_1", "gdpr", "P90D",
                ),
                "enterprise_trace_id": TRACE_ID, "retention_policy": "P90D",
            }
        ]
        result = asyncio.run(auditor.validate_gdpr_soc2_compliance("t1", "gdpr", entries, TRACE_ID))
        assert result["compliant"] is True

    def test_missing_trace_id_is_violation(self) -> None:
        auditor = ComplianceAuditor()
        entries = [
            {
                "entry_id": "e1", "tenant_id": "t1", "action": "run",
                "actor": "alice", "target_resource": "dag_1",
                "compliance_hash": "hash", "enterprise_trace_id": "",
                "retention_policy": "P90D",
            }
        ]
        result = asyncio.run(auditor.validate_gdpr_soc2_compliance("t1", "gdpr", entries, TRACE_ID))
        assert result["compliant"] is False
        assert any("enterprise_trace_id" in v for v in result["violations"])

    def test_hash_mismatch_is_violation(self) -> None:
        auditor = ComplianceAuditor()
        entries = [
            {
                "entry_id": "e1", "tenant_id": "t1", "action": "run",
                "actor": "alice", "target_resource": "dag_1",
                "compliance_hash": "", "enterprise_trace_id": TRACE_ID,
                "retention_policy": "P90D",
            }
        ]
        result = asyncio.run(auditor.validate_gdpr_soc2_compliance("t1", "gdpr", entries, TRACE_ID))
        assert result["compliant"] is False
        assert any("compliance_hash" in v for v in result["violations"])

    def test_compliance_report_generates(self) -> None:
        auditor = ComplianceAuditor()
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        result = asyncio.run(auditor.generate_compliance_report("t1", "gdpr", period[0], period[1], TRACE_ID))
        assert result["status"] in ("PASS", "FLAG", "FAIL")
        assert result["report_id"].startswith("cr_")


# ── TestEventBusPropagation (3 tests) ──────────────────────────


class TestEventBusPropagation:
    """Events published to correct enterprise topics."""

    def test_router_publishes_routing_event(self) -> None:
        bus = InMemoryEventBus()
        router = TenantRouter(strict_enterprise_mode=True, event_bus=bus)
        router.register_tenant("t1", "strict")
        asyncio.run(router.route_request("t1", {"target_tenant": "t1"}, TRACE_ID))
        events = bus.get_events("enterprise.routing")
        assert len(events) >= 1

    def test_meter_publishes_recording_event(self) -> None:
        bus = InMemoryEventBus()
        meter = UsageMeter(strict_enterprise_mode=True, event_bus=bus)
        asyncio.run(meter.record_operation("t1", "dag_execution", Decimal("10"), TRACE_ID))
        events = bus.get_events("enterprise.usage")
        assert len(events) >= 1

    def test_billing_publishes_invoice_event(self) -> None:
        bus = InMemoryEventBus()
        engine = BillingEngine(strict_enterprise_mode=True, event_bus=bus)
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        asyncio.run(engine.generate_invoice(
            "t1", period[0], period[1],
            [{"operation_type": "dag_execution", "units": "100", "rate": "0.005", "subtotal": "0.50"}],
            Decimal("0.50"), TRACE_ID,
        ))
        events = bus.get_events("enterprise.billing")
        assert len(events) >= 1
