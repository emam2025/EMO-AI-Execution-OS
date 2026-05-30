"""Phase K3 — Enterprise Expansion Integration Tests.  # LAW-1 LAW-9 LAW-11 LAW-12 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

6 test groups covering Phase K1-K3 enterprise expansion:

  Group 1 — K3-1:  Usage Metering (record, aggregate, detect anomalies, flush)
  Group 2 — K3-2:  Billing Engine (tiers, invoices, payment states, suspend)
  Group 3 — K3-3:  Compliance Auditor (trails, validation, reports, archives)
  Group 4 — K3-4:  Trace Correlation (end-to-end propagation chain)
  Group 5 — K3-5:  Event Bus Propagation (routing, metering, billing, compliance)
  Group 6 — K3-6:  Anomaly Detection & Rollback (edge cases)

Ref: artifacts/design/j2/protocols/01_enterprise_protocols.py
Ref: EXEC-DIRECTIVE-024 §1-5
Ref: Canon LAW 1, 9, 11, 12, 23-27, RULE 1-5
"""

from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal
from typing import Any

from core.enterprise.usage_meter import UsageMeter
from core.enterprise.billing_engine import BillingEngine
from core.enterprise.compliance_auditor import ComplianceAuditor
from core.enterprise.trace_correlator import EnterpriseTraceCorrelator


TRACE_ID = "entr_k3_integration_001"


class InMemoryEventBus:
    def __init__(self) -> None:
        self._events: dict = {}

    def publish(self, topic: str, event: Any) -> None:
        if topic not in self._events:
            self._events[topic] = []
        self._events[topic].append(event)

    def get_events(self, topic: str) -> list:
        return self._events.get(topic, [])


# ═══════════════════════════════════════════════════════════════
# Group 1 — K3-1: Usage Metering
# ═══════════════════════════════════════════════════════════════


class TestK3UsageMetering:
    """K3-1: Record, aggregate, detect anomalies, flush."""

    def test_record_operation_buffers_correctly(self) -> None:
        meter = UsageMeter()
        r = asyncio.run(meter.record_operation("t1", "dag_execution", Decimal("10"), TRACE_ID))
        assert r["record_id"] is not None
        assert r["hash"] is not None
        assert r["buffered"] is True
        assert r["trace_id"] == TRACE_ID
        assert meter.get_buffer_size("t1") == 1

    def test_accumulate_usage_by_type(self) -> None:
        meter = UsageMeter()
        asyncio.run(meter.record_operation("t1", "dag_execution", Decimal("10"), TRACE_ID))
        asyncio.run(meter.record_operation("t1", "api_call", Decimal("5"), TRACE_ID))
        asyncio.run(meter.record_operation("t1", "dag_execution", Decimal("20"), TRACE_ID))
        totals = asyncio.run(meter.accumulate_usage_by_type("t1"))
        assert totals["dag_execution"] == Decimal("30")
        assert totals["api_call"] == Decimal("5")

    def test_aggregate_daily_usage(self) -> None:
        meter = UsageMeter()
        asyncio.run(meter.record_operation("t1", "dag_execution", Decimal("10"), TRACE_ID))
        asyncio.run(meter.record_operation("t1", "api_call", Decimal("5"), TRACE_ID))
        agg = asyncio.run(meter.aggregate_daily_usage("t1", datetime.date.today(), TRACE_ID))
        assert agg["tenant_id"] == "t1"
        assert agg["record_count"] == 2
        assert agg["total_units"] == Decimal("15")
        assert agg["trace_id"] == TRACE_ID

    def test_detect_anomalies_returns_false_for_normal(self) -> None:
        meter = UsageMeter()
        snapshot = {"totals": {"dag_execution": Decimal("100")}, "total_cost": Decimal("50")}
        result = asyncio.run(meter.detect_anomalies("t1", snapshot, TRACE_ID))
        assert result["anomalous"] is False
        assert result["trace_id"] == TRACE_ID

    def test_detect_anomalies_flags_high_usage(self) -> None:
        meter = UsageMeter()
        snapshot = {"totals": {"dag_execution": Decimal("100000")}, "total_cost": Decimal("50000")}
        result = asyncio.run(meter.detect_anomalies("t1", snapshot, TRACE_ID))
        assert result["anomalous"] is True
        assert len(result["flagged_ops"]) >= 1

    def test_flush_to_billing_clears_buffer(self) -> None:
        meter = UsageMeter()
        asyncio.run(meter.record_operation("t1", "dag_execution", Decimal("10"), TRACE_ID))
        asyncio.run(meter.record_operation("t1", "api_call", Decimal("5"), TRACE_ID))
        flush_result = asyncio.run(meter.flush_to_billing("t1", TRACE_ID))
        assert flush_result["flushed"] == 2
        assert flush_result["total_cost"] == Decimal("15")
        assert meter.get_buffer_size("t1") == 0

    def test_tenant_isolation_no_cross_leakage(self) -> None:
        meter = UsageMeter()
        asyncio.run(meter.record_operation("t1", "dag_execution", Decimal("10"), TRACE_ID))
        asyncio.run(meter.record_operation("t2", "api_call", Decimal("5"), TRACE_ID))
        t1_agg = asyncio.run(meter.aggregate_daily_usage("t1", datetime.date.today(), TRACE_ID))
        t2_agg = asyncio.run(meter.aggregate_daily_usage("t2", datetime.date.today(), TRACE_ID))
        assert t1_agg["record_count"] == 1
        assert t2_agg["record_count"] == 1
        assert t1_agg["total_units"] != t2_agg["total_units"]


# ═══════════════════════════════════════════════════════════════
# Group 2 — K3-2: Billing Engine
# ═══════════════════════════════════════════════════════════════


class TestK3BillingEngine:
    """K3-2: Pricing tiers, invoices, payment states, suspend."""

    def test_apply_pricing_tier_free_is_zero(self) -> None:
        engine = BillingEngine()
        usage = {"dag_execution": Decimal("100"), "api_call": Decimal("500")}
        result = asyncio.run(engine.apply_pricing_tier("t1", "free", usage, TRACE_ID))
        assert result["total"] == Decimal("0")
        assert result["currency"] == "USD"

    def test_apply_pricing_tier_enterprise_cheaper(self) -> None:
        engine = BillingEngine()
        usage = {"dag_execution": Decimal("1000")}
        starter = asyncio.run(engine.apply_pricing_tier("t1", "starter", usage, TRACE_ID))
        enterprise = asyncio.run(engine.apply_pricing_tier("t1", "enterprise", usage, TRACE_ID))
        assert starter["total"] > enterprise["total"]

    def test_generate_invoice_creates_valid_invoice(self) -> None:
        engine = BillingEngine()
        period = (datetime.date(2026, 5, 1), datetime.date(2026, 5, 31))
        line_items = [{"operation_type": "dag_execution", "units": "100", "rate": "0.005", "subtotal": "0.50"}]
        result = asyncio.run(engine.generate_invoice("t1", period[0], period[1], line_items, Decimal("0.50"), TRACE_ID))
        assert result["invoice_id"].startswith("INV-")
        assert result["payment_state"] == "pending"
        assert result["due_date"] is not None
        assert result["trace_id"] == TRACE_ID

    def test_generate_invoice_rejects_negative_amount(self) -> None:
        engine = BillingEngine()
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        result = asyncio.run(engine.generate_invoice(
            "t1", period[0], period[1], [], Decimal("-50"), TRACE_ID,
        ))
        assert result.get("error") == "Negative invoice amount"

    def test_process_payment_state_valid_transition(self) -> None:
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

    def test_process_payment_state_invalid_transition(self) -> None:
        engine = BillingEngine()
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        inv = asyncio.run(engine.generate_invoice(
            "t1", period[0], period[1],
            [{"operation_type": "dag_execution", "units": "100", "rate": "0.005", "subtotal": "0.50"}],
            Decimal("0.50"), TRACE_ID,
        ))
        r = asyncio.run(engine.process_payment_state(inv["invoice_id"], "t1", "paid", TRACE_ID))
        assert r["allowed"] is False

    def test_suspend_on_default_within_grace(self) -> None:
        engine = BillingEngine()
        result = asyncio.run(engine.suspend_on_default("t1", ["inv1"], TRACE_ID))
        assert result["suspended"] is False

    def test_suspend_on_default_after_grace(self) -> None:
        engine = BillingEngine()
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        for _ in range(3):
            asyncio.run(engine.generate_invoice(
                "t1", period[0], period[1],
                [{"operation_type": "dag_execution", "units": "100", "rate": "0.005", "subtotal": "0.50"}],
                Decimal("0.50"), TRACE_ID,
            ))
        result = asyncio.run(engine.suspend_on_default(
            "t1", ["inv_1", "inv_2", "inv_3", "inv_4", "inv_5", "inv_6", "inv_7"], TRACE_ID,
        ))
        assert result["suspended"] is True
        assert result["suspended_at_ns"] > 0

    def test_rollback_invoice(self) -> None:
        engine = BillingEngine()
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        inv = asyncio.run(engine.generate_invoice(
            "t1", period[0], period[1],
            [{"operation_type": "dag_execution", "units": "100", "rate": "0.005", "subtotal": "0.50"}],
            Decimal("0.50"), TRACE_ID,
        ))
        result = asyncio.run(engine.rollback_invoice(inv["invoice_id"]))
        assert result["rolled_back"] is True

    def test_get_invoices(self) -> None:
        engine = BillingEngine()
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        asyncio.run(engine.generate_invoice(
            "t1", period[0], period[1],
            [{"operation_type": "dag_execution", "units": "100", "rate": "0.005", "subtotal": "0.50"}],
            Decimal("0.50"), TRACE_ID,
        ))
        invoices = engine.get_invoices("t1")
        assert len(invoices) == 1


# ═══════════════════════════════════════════════════════════════
# Group 3 — K3-3: Compliance Auditor
# ═══════════════════════════════════════════════════════════════


class TestK3ComplianceAuditor:
    """K3-3: Audit trails, validation, reports, archives."""

    def test_collect_audit_trail(self) -> None:
        auditor = ComplianceAuditor()
        result = asyncio.run(auditor.collect_audit_trail("t1", "run", "alice", "dag_1", TRACE_ID))
        assert result["entry_id"] is not None
        assert result["hash"] is not None
        assert result["compliance_hash"] is not None
        assert result["trace_id"] == TRACE_ID

    def test_valid_entries_pass_validation(self) -> None:
        auditor = ComplianceAuditor()
        e1 = asyncio.run(auditor.collect_audit_trail("t1", "run", "alice", "dag_1", TRACE_ID))
        entries = [
            {"entry_id": e1["entry_id"], "compliance_hash": e1["compliance_hash"],
             "enterprise_trace_id": TRACE_ID},
        ]
        result = asyncio.run(auditor.validate_gdpr_soc2_compliance("t1", "gdpr", entries, TRACE_ID))
        assert result["compliant"] is True
        assert result["framework"] == "gdpr"

    def test_missing_trace_id_is_violation(self) -> None:
        auditor = ComplianceAuditor()
        entries = [
            {"entry_id": "e1", "compliance_hash": "hash", "enterprise_trace_id": ""},
        ]
        result = asyncio.run(auditor.validate_gdpr_soc2_compliance("t1", "gdpr", entries, TRACE_ID))
        assert result["compliant"] is False

    def test_compliance_report_generates(self) -> None:
        auditor = ComplianceAuditor()
        asyncio.run(auditor.collect_audit_trail("t1", "run", "alice", "dag_1", TRACE_ID))
        period = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        result = asyncio.run(auditor.generate_compliance_report("t1", "gdpr", period[0], period[1], TRACE_ID))
        assert result["status"] in ("PASS", "FLAG", "FAIL")
        assert result["report_id"].startswith("cr_")
        assert result["trace_id"] == TRACE_ID

    def test_archive_logs_retains_recent(self) -> None:
        auditor = ComplianceAuditor()
        asyncio.run(auditor.collect_audit_trail("t1", "run", "alice", "dag_1", TRACE_ID))
        result = asyncio.run(auditor.archive_logs("t1", "P30D"))
        assert result["policy"] == "P30D"
        assert result["retained_count"] >= 0

    def test_verify_chain_integrity_passes(self) -> None:
        auditor = ComplianceAuditor()
        asyncio.run(auditor.collect_audit_trail("t1", "run", "alice", "dag_1", TRACE_ID))
        asyncio.run(auditor.collect_audit_trail("t1", "deploy", "bob", "dag_2", TRACE_ID))
        result = asyncio.run(auditor.verify_chain_integrity())
        assert result["valid"] is True
        assert result["total_entries"] == 2

    def test_get_entries_by_tenant(self) -> None:
        auditor = ComplianceAuditor()
        asyncio.run(auditor.collect_audit_trail("t1", "run", "alice", "dag_1", TRACE_ID))
        asyncio.run(auditor.collect_audit_trail("t2", "deploy", "bob", "dag_2", TRACE_ID))
        t1_entries = auditor.get_entries("t1")
        assert len(t1_entries) == 1
        assert t1_entries[0]["tenant_id"] == "t1"


# ═══════════════════════════════════════════════════════════════
# Group 4 — K3-4: Trace Correlation (End-to-End)
# ═══════════════════════════════════════════════════════════════


class TestK3TraceCorrelation:
    """K3-4: Enterprise trace_id propagates through all K3 layers."""

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
        usage = {"dag_execution": Decimal("100")}
        asyncio.run(engine.apply_pricing_tier("t1", "professional", usage, tid))
        chain = tc.trace_chain(tid)
        assert "billing_engine" in chain.get("layers", {})

    def test_auditor_records_trace(self) -> None:
        tc = EnterpriseTraceCorrelator()
        auditor = ComplianceAuditor(trace_correlator=tc)
        tid = tc.generate_enterprise_trace_id("sess", "t1")
        asyncio.run(auditor.collect_audit_trail("t1", "run", "alice", "dag_1", tid))
        chain = tc.trace_chain(tid)
        assert "compliance_auditor" in chain.get("layers", {})

    def test_end_to_end_meter_billing_audit(self) -> None:
        tc = EnterpriseTraceCorrelator()
        meter = UsageMeter(trace_correlator=tc)
        engine = BillingEngine(trace_correlator=tc)
        auditor = ComplianceAuditor(trace_correlator=tc)
        tid = tc.generate_enterprise_trace_id("sess", "t1")
        asyncio.run(meter.record_operation("t1", "dag_execution", Decimal("10"), tid))
        asyncio.run(meter.record_operation("t1", "api_call", Decimal("5"), tid))
        usage = asyncio.run(meter.aggregate_daily_usage("t1", datetime.date.today(), tid))
        asyncio.run(engine.apply_pricing_tier("t1", "professional", usage["totals"], tid))
        asyncio.run(auditor.collect_audit_trail("t1", "billing_run", "system", "invoice_gen", tid))
        chain = tc.trace_chain(tid)
        layers = chain.get("layers", {})
        assert "usage_meter" in layers
        assert "billing_engine" in layers
        assert "compliance_auditor" in layers


# ═══════════════════════════════════════════════════════════════
# Group 5 — K3-5: Event Bus Propagation
# ═══════════════════════════════════════════════════════════════


class TestK3EventBusPropagation:
    """K3-5: Events published to correct enterprise topics."""

    def test_meter_publishes_event(self) -> None:
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

    def test_compliance_publishes_event(self) -> None:
        bus = InMemoryEventBus()
        auditor = ComplianceAuditor(strict_enterprise_mode=True, event_bus=bus)
        asyncio.run(auditor.collect_audit_trail("t1", "run", "alice", "dag_1", TRACE_ID))
        events = bus.get_events("enterprise.compliance")
        assert len(events) >= 1


# ═══════════════════════════════════════════════════════════════
# Group 6 — K3-6: Anomaly Detection & Rollback Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestK3AnomalyAndRollback:
    """K3-6: Edge cases for anomaly detection and rollback."""

    def test_anomaly_zero_usage(self) -> None:
        meter = UsageMeter()
        snapshot = {"totals": {}, "total_cost": Decimal("0")}
        result = asyncio.run(meter.detect_anomalies("t1", snapshot, TRACE_ID))
        assert result["anomalous"] is False

    def test_anomaly_flagged_ops_single(self) -> None:
        meter = UsageMeter()
        snapshot = {"totals": {"storage_gb": Decimal("100000")}, "total_cost": Decimal("100")}
        result = asyncio.run(meter.detect_anomalies("t1", snapshot, TRACE_ID))
        assert "storage_gb" in result["flagged_ops"]

    def test_anomaly_trace_id_echoed(self) -> None:
        meter = UsageMeter()
        snapshot = {"totals": {}, "total_cost": Decimal("0")}
        result = asyncio.run(meter.detect_anomalies("t1", snapshot, TRACE_ID))
        assert result["trace_id"] == TRACE_ID

    def test_rollback_nonexistent_invoice(self) -> None:
        engine = BillingEngine()
        result = asyncio.run(engine.rollback_invoice("nonexistent"))
        assert result["rolled_back"] is False
        assert result["reason"] == "Invoice not found"

    def test_process_payment_state_nonexistent(self) -> None:
        engine = BillingEngine()
        result = asyncio.run(engine.process_payment_state("bad_id", "t1", "processing", TRACE_ID))
        assert result["allowed"] is False

    def test_compliance_chain_integrity_empty(self) -> None:
        auditor = ComplianceAuditor()
        result = asyncio.run(auditor.verify_chain_integrity())
        assert result["valid"] is True
        assert result["total_entries"] == 0
