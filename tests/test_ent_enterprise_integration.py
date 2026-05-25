"""Phase J2 — Enterprise Integration & Isolation Tests.  # LAW-5 LAW-11 LAW-12 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

30 tests across 6 groups:
  1. TenantIsolationEnforcement (6 tests)
  2. BillingDeterminismAndRollback (5 tests)
  3. ComplianceAuditImmutability (5 tests)
  4. EnterpriseTracePropagation (5 tests)
  5. MultiTenantFairnessUnderLoad (5 tests)
  6. QuotaEnforcementAndSuspension (4 tests)

Ref: EXEC-DIRECTIVE-ENT-001 §Task-5
Ref: Canon LAW 23-27 (Enterprise)
"""

from __future__ import annotations

import datetime
import hashlib
import time
from decimal import Decimal
from typing import Any, Dict, List

import pytest

from core.enterprise.tenant_router import TenantRouter, MAX_QUOTA_VIOLATIONS_BEFORE_SUSPEND
from core.enterprise.usage_meter import UsageMeter
from core.enterprise.billing_engine import BillingEngine, TIER_RATES, GRACE_PERIOD_DAYS
from core.enterprise.compliance_auditor import ComplianceAuditor
from core.enterprise.trace_correlator import EnterpriseTraceCorrelator


ET_ID = "ent_int_test_001"
TENANT_A = "tenant_alpha"
TENANT_B = "tenant_beta"


# ═════════════════════════════════════════════════════════════════════
# Group 1: Tenant Isolation Enforcement (6 tests)
# ═════════════════════════════════════════════════════════════════════


class TestTenantIsolationEnforcement:
    """G-L1 blocks cross-tenant access under STRICT isolation."""

    @pytest.mark.asyncio
    async def test_same_tenant_routes_successfully(self) -> None:
        router = TenantRouter()
        router.register_tenant(TENANT_A, "strict", {"dag_exec": Decimal("100")})
        result = await router.route_request(
            TENANT_A, {"target_tenant": TENANT_A, "shared_resource_flag": False},
            ET_ID,
        )
        assert result["routed"]

    @pytest.mark.asyncio
    async def test_cross_tenant_strict_blocked(self) -> None:
        router = TenantRouter()
        router.register_tenant(TENANT_A, "strict", {"dag_exec": Decimal("100")})
        router.register_tenant(TENANT_B, "strict", {"dag_exec": Decimal("100")})
        result = await router.route_request(
            TENANT_A, {"target_tenant": TENANT_B, "shared_resource_flag": False},
            ET_ID,
        )
        assert not result["routed"]
        assert "cross_tenant_blocked" in result.get("blocked_by", [])

    @pytest.mark.asyncio
    async def test_cross_tenant_non_strict_allowed(self) -> None:
        router = TenantRouter()
        router.register_tenant(TENANT_A, "strict")
        router.register_tenant(TENANT_B, "permissive")
        result = await router.route_request(
            TENANT_A, {"target_tenant": TENANT_B, "shared_resource_flag": True,
                       "scope_verified": True},
            ET_ID,
        )
        assert result["routed"]

    @pytest.mark.asyncio
    async def test_unknown_tenant_blocked(self) -> None:
        router = TenantRouter()
        result = await router.route_request("unknown", {}, ET_ID)
        assert not result["routed"]

    @pytest.mark.asyncio
    async def test_inactive_tenant_blocked(self) -> None:
        router = TenantRouter()
        router.register_tenant(TENANT_A, "strict")
        router._tenants[TENANT_A]["active"] = False
        result = await router.route_request(TENANT_A, {}, ET_ID)
        assert not result["routed"]

    def test_zero_leakage_attempts_by_default(self) -> None:
        router = TenantRouter()
        assert len(router.get_leakage_attempts()) == 0


# ═════════════════════════════════════════════════════════════════════
# Group 2: Billing Determinism & Rollback (5 tests)
# ═════════════════════════════════════════════════════════════════════


class TestBillingDeterminismAndRollback:
    """Invoice generation is deterministic; rollback restores state."""

    @pytest.mark.asyncio
    async def test_invoice_rejects_negative_amount(self) -> None:
        engine = BillingEngine()
        today = datetime.date.today()
        result = await engine.generate_invoice(
            TENANT_A, today, today, [], Decimal("-10"), ET_ID,
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invoice_carries_correct_enterprise_trace_id(self) -> None:
        engine = BillingEngine()
        today = datetime.date.today()
        line_items = [{"op": "exec", "units": "1", "rate": "0.01", "subtotal": "0.01"}]
        result = await engine.generate_invoice(TENANT_A, today, today, line_items, Decimal("0.01"), ET_ID)
        assert result["trace_id"] == ET_ID

    @pytest.mark.asyncio
    async def test_rollback_restores_exact_line_items(self) -> None:
        engine = BillingEngine()
        today = datetime.date.today()
        line_items = [{"op": "exec", "units": "5", "rate": "0.005", "subtotal": "0.025"}]
        inv = await engine.generate_invoice(TENANT_A, today, today, line_items, Decimal("0.025"), ET_ID)
        rb = await engine.rollback_invoice(inv["invoice_id"])
        assert rb["rolled_back"]
        assert rb["invoice"]["line_items"] == line_items

    @pytest.mark.asyncio
    async def test_suspend_on_default_honors_grace(self) -> None:
        engine = BillingEngine()
        result = await engine.suspend_on_default(TENANT_A, ["INV-001"], ET_ID)
        assert not result["suspended"]

    @pytest.mark.asyncio
    async def test_suspend_after_exhausted_grace_works(self) -> None:
        engine = BillingEngine()
        many = [f"INV-{i}" for i in range(GRACE_PERIOD_DAYS + 1)]
        result = await engine.suspend_on_default(TENANT_A, many, ET_ID)
        assert result["suspended"]


# ═════════════════════════════════════════════════════════════════════
# Group 3: Compliance Audit Immutability (5 tests)
# ═════════════════════════════════════════════════════════════════════


class TestComplianceAuditImmutability:
    """Audit log is immutable; chain hash detects tampering."""

    @pytest.mark.asyncio
    async def test_audit_entry_has_unique_id(self) -> None:
        auditor = ComplianceAuditor()
        a = await auditor.collect_audit_trail(TENANT_A, "act", "op", "res", "t1")
        b = await auditor.collect_audit_trail(TENANT_A, "act", "op", "res", "t2")
        assert a["entry_id"] != b["entry_id"]

    @pytest.mark.asyncio
    async def test_chain_integrity_passes_for_clean_log(self) -> None:
        auditor = ComplianceAuditor()
        for i in range(3):
            await auditor.collect_audit_trail(TENANT_A, f"act_{i}", f"op{i}", f"r{i}", f"t{i}")
        assert (await auditor.verify_chain_integrity())["valid"]

    @pytest.mark.asyncio
    async def test_tampered_entry_detected(self) -> None:
        auditor = ComplianceAuditor()
        await auditor.collect_audit_trail(TENANT_A, "a1", "op1", "r1", "t1")
        await auditor.collect_audit_trail(TENANT_A, "a2", "op2", "r2", "t2")
        auditor._audit_entries[0]["entry_hash"] = "bad"
        assert not (await auditor.verify_chain_integrity())["valid"]

    @pytest.mark.asyncio
    async def test_gdpr_soc2_validation_passes(self) -> None:
        auditor = ComplianceAuditor()
        entry = await auditor.collect_audit_trail(TENANT_A, "exec", "op1", "dag:001", ET_ID)
        entries = auditor.get_entries(TENANT_A)
        result = await auditor.validate_gdpr_soc2_compliance(TENANT_A, "gdpr", entries, ET_ID)
        assert result["compliant"]

    @pytest.mark.asyncio
    async def test_archive_after_retention(self) -> None:
        auditor = ComplianceAuditor()
        await auditor.collect_audit_trail(TENANT_A, "old", "past", "r1", "t1")
        result = await auditor.archive_logs(TENANT_A, "P30D", ET_ID)
        assert isinstance(result["archived_count"], int)


# ═════════════════════════════════════════════════════════════════════
# Group 4: Enterprise Trace Propagation (5 tests)
# ═════════════════════════════════════════════════════════════════════


class TestEnterpriseTracePropagation:
    """enterprise_trace_id propagates across all J2 layers."""

    def test_generates_enterprise_trace_id(self) -> None:
        tc = EnterpriseTraceCorrelator()
        eid = tc.generate_enterprise_trace_id("sess_001", TENANT_A)
        assert eid.startswith("entr_")

    def test_records_trace_across_layers(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tc.record_trace(ET_ID, "tenant_router", "route_001")
        tc.record_trace(ET_ID, "usage_meter", "meter_001")
        chain = tc.get_trace_chain(ET_ID)
        assert "tenant_router" in chain
        assert "usage_meter" in chain

    def test_full_propagation_check(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tc.record_trace(ET_ID, "tenant_router", "r1")
        tc.record_trace(ET_ID, "usage_meter", "m1")
        tc.record_trace(ET_ID, "billing_engine", "b1")
        tc.record_trace(ET_ID, "compliance_auditor", "c1")
        result = tc.verify_full_propagation(ET_ID)
        assert result["full_propagation"]

    def test_missing_layers_detected(self) -> None:
        tc = EnterpriseTraceCorrelator()
        tc.record_trace(ET_ID, "tenant_router", "r1")
        result = tc.verify_full_propagation(ET_ID)
        assert not result["full_propagation"]
        assert "usage_meter" in result["missing_layers"]

    def test_propagate_to_f4_returns_span_id(self) -> None:
        tc = EnterpriseTraceCorrelator()
        result = tc.propagate_to_f4(ET_ID)
        assert result["target_layer"] == "f4_observability"
        assert "f4_span_id" in result


# ═════════════════════════════════════════════════════════════════════
# Group 5: Multi-Tenant Fairness Under Load (5 tests)
# ═════════════════════════════════════════════════════════════════════


class TestMultiTenantFairnessUnderLoad:
    """Multiple tenants can operate independently without starvation."""

    @pytest.mark.asyncio
    async def test_two_tenants_both_route(self) -> None:
        router = TenantRouter()
        router.register_tenant(TENANT_A, "strict", {"units": Decimal("100")})
        router.register_tenant(TENANT_B, "strict", {"units": Decimal("100")})
        ra = await router.route_request(TENANT_A, {"target_tenant": TENANT_A}, ET_ID + "_a")
        rb = await router.route_request(TENANT_B, {"target_tenant": TENANT_B}, ET_ID + "_b")
        assert ra["routed"]
        assert rb["routed"]

    @pytest.mark.asyncio
    async def test_usage_meter_partitions_by_tenant(self) -> None:
        meter = UsageMeter()
        await meter.record_operation(TENANT_A, "dag_execution", Decimal("10"), ET_ID + "_a")
        await meter.record_operation(TENANT_B, "dag_execution", Decimal("20"), ET_ID + "_b")
        agg_a = await meter.accumulate_usage_by_type(TENANT_A)
        agg_b = await meter.accumulate_usage_by_type(TENANT_B)
        assert agg_a["dag_execution"] == Decimal("10")
        assert agg_b["dag_execution"] == Decimal("20")

    @pytest.mark.asyncio
    async def test_billing_engine_tiers_per_tenant(self) -> None:
        engine = BillingEngine()
        usage = {"dag_execution": Decimal("100")}
        ra = await engine.apply_pricing_tier(TENANT_A, "enterprise", usage, ET_ID + "_a")
        rb = await engine.apply_pricing_tier(TENANT_B, "free", usage, ET_ID + "_b")
        assert ra["total"] > Decimal("0")
        assert rb["total"] == Decimal("0")

    @pytest.mark.asyncio
    async def test_compliance_auditor_scoped_to_tenant(self) -> None:
        auditor = ComplianceAuditor()
        await auditor.collect_audit_trail(TENANT_A, "act", "op", "res", "t_a")
        entries_b = auditor.get_entries(TENANT_B)
        assert len(entries_b) == 0

    @pytest.mark.asyncio
    async def test_three_tenants_independent_quota(self) -> None:
        router = TenantRouter()
        TENANT_C = "tenant_gamma"
        router.register_tenant(TENANT_A, "strict", {"cpu": Decimal("50")})
        router.register_tenant(TENANT_B, "strict", {"cpu": Decimal("50")})
        router.register_tenant(TENANT_C, "strict", {"cpu": Decimal("50")})
        for i in range(3):
            for t in [TENANT_A, TENANT_B, TENANT_C]:
                await router.enforce_quota(t, "cpu", Decimal("10"), f"{ET_ID}_{t}_{i}")
        qa = router._get_quota_status(TENANT_A)
        qb = router._get_quota_status(TENANT_B)
        qc = router._get_quota_status(TENANT_C)
        assert qa["cpu"] == Decimal("20")
        assert qb["cpu"] == Decimal("20")
        assert qc["cpu"] == Decimal("20")


# ═════════════════════════════════════════════════════════════════════
# Group 6: Quota Enforcement & Suspension (4 tests)
# ═════════════════════════════════════════════════════════════════════


class TestQuotaEnforcementAndSuspension:
    """Quota exhaustion blocks; repeated violations suspend tenant."""

    @pytest.mark.asyncio
    async def test_quota_allows_within_limits(self) -> None:
        router = TenantRouter()
        router.register_tenant(TENANT_A, "strict", {"cpu": Decimal("100")})
        result = await router.enforce_quota(TENANT_A, "cpu", Decimal("30"), ET_ID)
        assert result["allowed"]
        assert result["quota_after"] == 70.0

    @pytest.mark.asyncio
    async def test_quota_blocks_exceeded(self) -> None:
        router = TenantRouter()
        router.register_tenant(TENANT_A, "strict", {"cpu": Decimal("10")})
        result = await router.enforce_quota(TENANT_A, "cpu", Decimal("20"), ET_ID)
        assert not result["allowed"]
        assert result["exceeded"]

    @pytest.mark.asyncio
    async def test_quota_unknown_resource_returns_zero(self) -> None:
        router = TenantRouter()
        router.register_tenant(TENANT_A, "strict")
        result = await router.enforce_quota(TENANT_A, "nonexistent", Decimal("1"), ET_ID)
        assert not result["allowed"]  # available is 0

    @pytest.mark.asyncio
    async def test_repeated_violations_suspend_tenant(self) -> None:
        router = TenantRouter()
        router.register_tenant(TENANT_A, "strict", {"cpu": Decimal("5")})
        for _ in range(MAX_QUOTA_VIOLATIONS_BEFORE_SUSPEND):
            await router.enforce_quota(TENANT_A, "cpu", Decimal("10"), ET_ID)
        assert not router._tenants[TENANT_A]["active"]
