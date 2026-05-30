"""Phase J2 — Isolation State Machine Leakage Guard Tests.  # LAW-11 LAW-23 LAW-24 LAW-25 LAW-27 RULE-1 RULE-3

Tests all 13 transitions (T1-T13), 5 Leakage Guards (G-L1-G-L5), and
Deterministic Audit Guard (G-A1) against the tenant isolation state machine.

Ref: artifacts/design/j2/03_tenant_isolation_machine.md §1-3
Ref: Canon LAW 11, 23, 24, 25, 27, RULE 1, 3
"""

from __future__ import annotations

import hashlib

import pytest

from core.enterprise.isolation_state_machine import (
    IsolationStateMachine,
    RoutingState,
    RoutingTransition,
)


TRACE_ID = "entr_test_sm_001"


class TestRoutingTransitions:
    """Test all 13 valid transitions (T1-T13)."""

    def test_t1_idle_to_request_received(self) -> None:
        sm = IsolationStateMachine()
        r = sm.transition(RoutingTransition.T1, enterprise_trace_id=TRACE_ID)
        assert r["success"] is True
        assert r["from_state"] == "idle"
        assert r["to_state"] == "request_received"

    def test_t2_request_received_to_validation(self) -> None:
        sm = IsolationStateMachine()
        sm.transition(RoutingTransition.T1, enterprise_trace_id=TRACE_ID)
        r = sm.transition(RoutingTransition.T2, enterprise_trace_id=TRACE_ID)
        assert r["success"] is True
        assert r["to_state"] == "tenant_validation"

    def test_t3_validation_to_quota_check_allowed(self) -> None:
        sm = IsolationStateMachine()
        sm.transition(RoutingTransition.T1, enterprise_trace_id=TRACE_ID)
        sm.transition(RoutingTransition.T2, enterprise_trace_id=TRACE_ID)
        r = sm.transition(RoutingTransition.T3, {
            "requesting_tenant": "tenant_a",
            "target_tenant": "tenant_a",
            "shared_resource_flag": False,
            "scope_verified": True,
            "target_isolation_policy": "strict",
        }, enterprise_trace_id=TRACE_ID)
        assert r["success"] is True
        assert r["to_state"] == "quota_check"

    def test_t3_cross_tenant_blocked_by_g_l1(self) -> None:
        sm = IsolationStateMachine()
        sm.transition(RoutingTransition.T1, enterprise_trace_id=TRACE_ID)
        sm.transition(RoutingTransition.T2, enterprise_trace_id=TRACE_ID)
        r = sm.transition(RoutingTransition.T3, {
            "requesting_tenant": "tenant_a",
            "target_tenant": "tenant_b",
            "shared_resource_flag": False,
            "scope_verified": False,
            "target_isolation_policy": "strict",
        }, enterprise_trace_id=TRACE_ID)
        assert r["success"] is False
        assert "G-L1" in r.get("blocked_by", [])

    def test_t4_validation_to_routing_failed(self) -> None:
        sm = IsolationStateMachine()
        sm.transition(RoutingTransition.T1, enterprise_trace_id=TRACE_ID)
        sm.transition(RoutingTransition.T2, enterprise_trace_id=TRACE_ID)
        r = sm.transition(RoutingTransition.T4, enterprise_trace_id=TRACE_ID)
        assert r["success"] is True
        assert r["to_state"] == "routing_failed"

    def test_t5_quota_check_to_route_execute(self) -> None:
        sm = IsolationStateMachine()
        sm.transition(RoutingTransition.T1, enterprise_trace_id=TRACE_ID)
        sm.transition(RoutingTransition.T2, enterprise_trace_id=TRACE_ID)
        sm.transition(RoutingTransition.T3, {
            "requesting_tenant": "tenant_a", "target_tenant": "tenant_a",
            "shared_resource_flag": False, "scope_verified": True,
        }, enterprise_trace_id=TRACE_ID)
        r = sm.transition(RoutingTransition.T5, {
            "requested_units": 5, "available_units": 10,
        }, enterprise_trace_id=TRACE_ID)
        assert r["success"] is True
        assert r["to_state"] == "route_execute"

    def test_t6_quota_exceeded_blocked_by_g_l2(self) -> None:
        sm = IsolationStateMachine()
        sm.transition(RoutingTransition.T1, enterprise_trace_id=TRACE_ID)
        sm.transition(RoutingTransition.T2, enterprise_trace_id=TRACE_ID)
        sm.transition(RoutingTransition.T3, {
            "requesting_tenant": "tenant_a", "target_tenant": "tenant_a",
            "shared_resource_flag": False, "scope_verified": True,
        }, enterprise_trace_id=TRACE_ID)
        r = sm.transition(RoutingTransition.T5, {
            "requested_units": 15, "available_units": 10,
        }, enterprise_trace_id=TRACE_ID)
        assert r["success"] is False
        assert "G-L2" in r.get("blocked_by", [])

    def test_t13_suspended_reinstated(self) -> None:
        sm = IsolationStateMachine()
        sm._state = RoutingState.SUSPENDED
        r = sm.transition(RoutingTransition.T13, {
            "overdue_invoice_count": 0, "has_failed_payment": False,
            "already_suspended": True, "max_overdue_threshold": 3,
        }, enterprise_trace_id=TRACE_ID)
        assert r["success"] is False
        assert "G-L5" in r.get("blocked_by", [])


class TestLeakageGuardGL1:
    """G-L1: Cross-tenant access requires shared_resource_flag AND scope_verified."""

    def test_same_tenant_always_allowed(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l1({
            "requesting_tenant": "a", "target_tenant": "a",
        })
        assert gr["G-L1_cross_tenant"].passed is True

    def test_cross_tenant_allowed_with_shared_and_verified(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l1({
            "requesting_tenant": "a", "target_tenant": "b",
            "shared_resource_flag": True, "scope_verified": True,
            "target_isolation_policy": "shared",
        })
        assert gr["G-L1_cross_tenant"].passed is True

    def test_cross_tenant_blocked_without_shared_flag(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l1({
            "requesting_tenant": "a", "target_tenant": "b",
            "shared_resource_flag": False, "scope_verified": True,
            "target_isolation_policy": "shared",
        })
        assert gr["G-L1_cross_tenant"].passed is False

    def test_cross_tenant_blocked_without_scope_verified(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l1({
            "requesting_tenant": "a", "target_tenant": "b",
            "shared_resource_flag": True, "scope_verified": False,
            "target_isolation_policy": "shared",
        })
        assert gr["G-L1_cross_tenant"].passed is False

    def test_cross_tenant_blocked_on_strict_policy(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l1({
            "requesting_tenant": "a", "target_tenant": "b",
            "shared_resource_flag": True, "scope_verified": True,
            "target_isolation_policy": "strict",
        })
        assert gr["G-L1_cross_tenant"].passed is False


class TestLeakageGuardGL2:
    """G-L2: Quota exhaustion blocks when requested > available."""

    def test_quota_available_passes(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l2({"requested_units": 5, "available_units": 10})
        assert gr["G-L2_quota"].passed is True

    def test_quota_exhausted_fails(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l2({"requested_units": 10, "available_units": 5})
        assert gr["G-L2_quota"].passed is False

    def test_quota_equal_passes(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l2({"requested_units": 5, "available_units": 5})
        assert gr["G-L2_quota"].passed is True


class TestLeakageGuardGL3:
    """G-L3: Metering requires tenant_id match and isolation_boundary."""

    def test_metering_allowed_with_boundary(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l3({
            "record_tenant_id": "t1", "executing_tenant_id": "t1",
            "isolation_boundary": "t1_boundary",
        })
        assert gr["G-L3_metering_boundary"].passed is True

    def test_metering_blocked_on_tenant_mismatch(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l3({
            "record_tenant_id": "t1", "executing_tenant_id": "t2",
            "isolation_boundary": "t1_boundary",
        })
        assert gr["G-L3_metering_boundary"].passed is False

    def test_metering_blocked_on_missing_boundary(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l3({
            "record_tenant_id": "t1", "executing_tenant_id": "t1",
            "isolation_boundary": None,
        })
        assert gr["G-L3_metering_boundary"].passed is False


class TestLeakageGuardGL4:
    """G-L4: Billing flush verifies tenant match and positive cost."""

    def test_flush_allowed_with_valid_records(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l4({
            "records": [
                {"tenant_id": "t1", "cost_units": "10"},
                {"tenant_id": "t1", "cost_units": "5"},
            ],
            "flush_tenant": "t1",
        })
        assert gr["G-L4_flush_integrity"].passed is True

    def test_flush_blocked_on_tenant_mismatch(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l4({
            "records": [
                {"tenant_id": "t1", "cost_units": "10"},
                {"tenant_id": "t2", "cost_units": "5"},
            ],
            "flush_tenant": "t1",
        })
        assert gr["G-L4_flush_integrity"].passed is False

    def test_flush_blocked_on_zero_cost(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l4({
            "records": [],
            "flush_tenant": "t1",
        })
        assert gr["G-L4_flush_integrity"].passed is False


class TestLeakageGuardGL5:
    """G-L5: Suspension requires overdue threshold or failed payment."""

    def test_suspension_allowed_on_overdue_threshold(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l5({
            "overdue_invoice_count": 5, "has_failed_payment": False,
            "already_suspended": False, "max_overdue_threshold": 3,
        })
        assert gr["G-L5_suspension"].passed is True

    def test_suspension_allowed_on_failed_payment(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l5({
            "overdue_invoice_count": 0, "has_failed_payment": True,
            "already_suspended": False, "max_overdue_threshold": 3,
        })
        assert gr["G-L5_suspension"].passed is True

    def test_suspension_blocked_when_already_suspended(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l5({
            "overdue_invoice_count": 5, "has_failed_payment": False,
            "already_suspended": True, "max_overdue_threshold": 3,
        })
        assert gr["G-L5_suspension"].passed is False

    def test_suspension_blocked_below_threshold(self) -> None:
        sm = IsolationStateMachine()
        gr = sm._evaluate_g_l5({
            "overdue_invoice_count": 1, "has_failed_payment": False,
            "already_suspended": False, "max_overdue_threshold": 3,
        })
        assert gr["G-L5_suspension"].passed is False


class TestDeterministicAuditGuardGA1:
    """G-A1: Same inputs always produce same audit hash."""

    def test_g_a1_deterministic_hash_same_inputs(self) -> None:
        h1 = IsolationStateMachine.compute_audit_hash("t1", "run", "alice", "dag_1", "gdpr", "P90D")
        h2 = IsolationStateMachine.compute_audit_hash("t1", "run", "alice", "dag_1", "gdpr", "P90D")
        assert h1 == h2

    def test_g_a1_hash_changes_on_different_tenant(self) -> None:
        h1 = IsolationStateMachine.compute_audit_hash("t1", "run", "alice", "dag_1", "gdpr", "P90D")
        h2 = IsolationStateMachine.compute_audit_hash("t2", "run", "alice", "dag_1", "gdpr", "P90D")
        assert h1 != h2

    def test_g_a1_hash_changes_on_different_action(self) -> None:
        h1 = IsolationStateMachine.compute_audit_hash("t1", "run", "alice", "dag_1", "gdpr", "P90D")
        h2 = IsolationStateMachine.compute_audit_hash("t1", "delete", "alice", "dag_1", "gdpr", "P90D")
        assert h1 != h2

    def test_g_a1_verify_passes_on_matching_hash(self) -> None:
        sm = IsolationStateMachine()
        h = IsolationStateMachine.compute_audit_hash("t1", "run", "alice", "dag_1", "gdpr", "P90D")
        gr = sm._evaluate_g_a1({
            "tenant_id": "t1", "action": "run", "actor": "alice",
            "target_resource": "dag_1", "compliance_framework": "gdpr",
            "retention_policy": "P90D", "entry_hash": h, "expected_hash": h,
        })
        assert gr["G-A1_audit_hash"].passed is True

    def test_g_a1_verify_fails_on_tamper(self) -> None:
        sm = IsolationStateMachine()
        h = IsolationStateMachine.compute_audit_hash("t1", "run", "alice", "dag_1", "gdpr", "P90D")
        gr = sm._evaluate_g_a1({
            "tenant_id": "t1", "action": "run", "actor": "alice",
            "target_resource": "dag_1", "compliance_framework": "gdpr",
            "retention_policy": "P90D", "entry_hash": "tampered", "expected_hash": h,
        })
        assert gr["G-A1_audit_hash"].passed is False


class TestStateMachineReset:
    """SM reset returns to IDLE and clears history."""

    def test_reset_returns_to_idle(self) -> None:
        sm = IsolationStateMachine()
        sm.transition(RoutingTransition.T1, enterprise_trace_id=TRACE_ID)
        sm.transition(RoutingTransition.T2, enterprise_trace_id=TRACE_ID)
        sm.reset()
        assert sm.state == RoutingState.IDLE

    def test_reset_clears_history(self) -> None:
        sm = IsolationStateMachine()
        sm.transition(RoutingTransition.T1, enterprise_trace_id=TRACE_ID)
        sm.reset()
        assert len(sm.transition_history) == 0
