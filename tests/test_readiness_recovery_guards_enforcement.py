"""Phase J3 — Recovery Guards Enforcement Tests.  # LAW-3 LAW-5 LAW-8 LAW-11 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Tests for G-C1 Pre-Fault Health Guard, G-C2 Degradation Budget Guard,
G-C3 Recovery Verification Guard, and G-D1 Deterministic Load Guard.

Ref: artifacts/design/j3/03_chaos_recovery_machine.md §3-4
Ref: Canon LAW 3, 5, 8, 11, 20-22, RULE 1-5
"""

from __future__ import annotations

import asyncio

import pytest

from core.readiness.readiness_state_machine import (
    ReadinessStateMachine,
    ChaosState,
    ChaosTransition,
    LoadState,
    LoadTransition,
    CertificationGateState,
    CertificationGateTransition,
    evaluate_g_c1_pre_fault_health,
    evaluate_g_c2_degradation_budget,
    evaluate_g_c3_recovery_verification,
    evaluate_g_d1_deterministic_load,
)

TRACE_ID = "rdns_test_recovery_guards_001"


class TestG1PreFaultHealthGuard:
    """G-C1: Pre-fault health guard prevents injection on degraded service."""

    def test_allows_injection_on_healthy_service(self) -> None:
        result = evaluate_g_c1_pre_fault_health(
            health_score=1.0,
            error_rate_pct=0.0,
            is_already_degraded=False,
            expected_recovery_sec=30.0,
        )
        assert result.passed is True
        assert result.guard_name == "G-C1"

    def test_blocks_injection_on_low_health(self) -> None:
        result = evaluate_g_c1_pre_fault_health(
            health_score=0.5,
            error_rate_pct=0.0,
            is_already_degraded=False,
            expected_recovery_sec=30.0,
        )
        assert result.passed is False
        assert "health_score" in result.detail

    def test_blocks_injection_on_high_error_rate(self) -> None:
        result = evaluate_g_c1_pre_fault_health(
            health_score=1.0,
            error_rate_pct=15.0,
            is_already_degraded=False,
            expected_recovery_sec=30.0,
        )
        assert result.passed is False
        assert "error_rate" in result.detail

    def test_blocks_injection_on_degraded_service(self) -> None:
        result = evaluate_g_c1_pre_fault_health(
            health_score=1.0,
            error_rate_pct=0.0,
            is_already_degraded=True,
            expected_recovery_sec=30.0,
        )
        assert result.passed is False
        assert "degraded" in result.detail

    def test_blocks_injection_on_missing_recovery_sec(self) -> None:
        result = evaluate_g_c1_pre_fault_health(
            health_score=1.0,
            error_rate_pct=0.0,
            is_already_degraded=False,
            expected_recovery_sec=0.0,
        )
        assert result.passed is False
        assert "expected_recovery_sec" in result.detail


class TestG2DegradationBudgetGuard:
    """G-C2: Degradation budget guard escalates on excessive degradation."""

    def test_allows_auto_recovery_within_budget(self) -> None:
        result = evaluate_g_c2_degradation_budget(
            degradation_metric=0.1,
            recovery_time_remaining_sec=60.0,
            cascade_failure_detected=False,
            severity_propagation_contained=True,
        )
        assert result.passed is True

    def test_blocks_on_cascade_failure(self) -> None:
        result = evaluate_g_c2_degradation_budget(
            degradation_metric=0.1,
            recovery_time_remaining_sec=60.0,
            cascade_failure_detected=True,
            severity_propagation_contained=True,
        )
        assert result.passed is False
        assert "cascade" in result.detail

    def test_blocks_on_severity_breach(self) -> None:
        result = evaluate_g_c2_degradation_budget(
            degradation_metric=0.5,
            recovery_time_remaining_sec=5.0,
            cascade_failure_detected=False,
            severity_propagation_contained=False,
        )
        assert result.passed is False

    def test_escalates_when_degradation_exceeds_threshold(self) -> None:
        sm = ReadinessStateMachine()
        sm.transition_chaos(ChaosTransition.C_T1, {
            "health_score": 1.0, "error_rate_pct": 0.0,
            "is_already_degraded": False, "expected_recovery_sec": 30.0,
        }, TRACE_ID)
        sm.transition_chaos(ChaosTransition.C_T2, {}, TRACE_ID)
        result = sm.transition_chaos(ChaosTransition.C_T3, {
            "degradation_metric": 0.5,
            "recovery_time_remaining_sec": 5.0,
            "cascade_failure_detected": False,
            "severity_propagation_contained": True,
        }, TRACE_ID)
        assert result["to_state"] == "escalated"
        assert "G-C2" in result["blocked_by"]


class TestG3RecoveryVerificationGuard:
    """G-C3: Recovery guard blocks certification if integrity or p99 fails."""

    def test_allows_when_all_conditions_met(self) -> None:
        result = evaluate_g_c3_recovery_verification(
            data_integrity_verified=True,
            lease_transferred=True,
            audit_hash_match=True,
            p99_ms=150.0,
            oscillation_detected=False,
            rollback_safe=True,
            data_sync_lag_ms=100.0,
        )
        assert result.passed is True

    def test_blocks_on_data_integrity_failure(self) -> None:
        result = evaluate_g_c3_recovery_verification(
            data_integrity_verified=False,
            lease_transferred=True,
            audit_hash_match=True,
            p99_ms=150.0,
            oscillation_detected=False,
            rollback_safe=True,
            data_sync_lag_ms=100.0,
        )
        assert result.passed is False
        assert "data_integrity" in result.detail

    def test_blocks_on_p99_exceeding_threshold(self) -> None:
        result = evaluate_g_c3_recovery_verification(
            data_integrity_verified=True,
            lease_transferred=True,
            audit_hash_match=True,
            p99_ms=300.0,
            oscillation_detected=False,
            rollback_safe=True,
            data_sync_lag_ms=100.0,
        )
        assert result.passed is False
        assert "p99_ms" in result.detail

    def test_blocks_on_rollback_unsafe(self) -> None:
        result = evaluate_g_c3_recovery_verification(
            data_integrity_verified=True,
            lease_transferred=True,
            audit_hash_match=True,
            p99_ms=150.0,
            oscillation_detected=False,
            rollback_safe=False,
            data_sync_lag_ms=100.0,
        )
        assert result.passed is False
        assert "rollback_safe" in result.detail

    def test_blocks_on_data_sync_lag_exceeded(self) -> None:
        result = evaluate_g_c3_recovery_verification(
            data_integrity_verified=True,
            lease_transferred=True,
            audit_hash_match=True,
            p99_ms=150.0,
            oscillation_detected=False,
            rollback_safe=True,
            data_sync_lag_ms=600.0,
        )
        assert result.passed is False
        assert "data_sync_lag" in result.detail

    def test_blocks_on_oscillation(self) -> None:
        result = evaluate_g_c3_recovery_verification(
            data_integrity_verified=True,
            lease_transferred=True,
            audit_hash_match=True,
            p99_ms=150.0,
            oscillation_detected=True,
            rollback_safe=True,
            data_sync_lag_ms=100.0,
        )
        assert result.passed is False
        assert "oscillation" in result.detail


class TestG1DeterministicLoadGuard:
    """G-D1: Deterministic Load Guard enforces reproducible load curves."""

    def test_allows_matching_hashes(self) -> None:
        result = evaluate_g_d1_deterministic_load(
            profile_hash="abc123",
            cluster_state_hash="def456",
            expected_profile_hash="abc123",
        )
        assert result.passed is True

    def test_blocks_mismatched_hashes(self) -> None:
        result = evaluate_g_d1_deterministic_load(
            profile_hash="abc123",
            cluster_state_hash="def456",
            expected_profile_hash="xyz789",
        )
        assert result.passed is False

    def test_blocks_empty_profile_hash(self) -> None:
        result = evaluate_g_d1_deterministic_load(
            profile_hash="",
            cluster_state_hash="def456",
            expected_profile_hash="",
        )
        assert result.passed is False
        assert "empty" in result.detail

    def test_deterministic_load_sm_transition(self) -> None:
        sm = ReadinessStateMachine()
        result = sm.transition_load(LoadTransition.L_T1, {
            "profile_hash": "abc123",
            "cluster_state_hash": "def456",
            "expected_profile_hash": "abc123",
        }, TRACE_ID)
        assert result["success"] is True
        assert result["to_state"] == "generating"

    def test_load_sm_blocks_on_hash_mismatch(self) -> None:
        sm = ReadinessStateMachine()
        result = sm.transition_load(LoadTransition.L_T1, {
            "profile_hash": "abc123",
            "cluster_state_hash": "def456",
            "expected_profile_hash": "wrong",
        }, TRACE_ID)
        assert result["success"] is True
        assert result["to_state"] == "generating"
        assert "G-D1" in result["blocked_by"]


class TestChaosStateMachineTransitions:
    """Chaos SM: Full lifecycle with guard enforcement."""

    def test_full_chaos_cycle_pass(self) -> None:
        sm = ReadinessStateMachine()
        assert sm.chaos_state == ChaosState.BASELINE_CAPTURED
        sm.transition_chaos(ChaosTransition.C_T1, {
            "health_score": 1.0, "error_rate_pct": 0.0,
            "is_already_degraded": False, "expected_recovery_sec": 30.0,
        }, TRACE_ID)
        assert sm.chaos_state == ChaosState.FAULT_INJECTED
        sm.transition_chaos(ChaosTransition.C_T2, {}, TRACE_ID)
        assert sm.chaos_state == ChaosState.MONITOR_DEGRADATION
        sm.transition_chaos(ChaosTransition.C_T3, {
            "degradation_metric": 0.1,
            "recovery_time_remaining_sec": 60.0,
            "cascade_failure_detected": False,
            "severity_propagation_contained": True,
        }, TRACE_ID)
        assert sm.chaos_state == ChaosState.AUTO_RECOVERY
        sm.transition_chaos(ChaosTransition.C_T5, {
            "data_integrity_verified": True,
            "lease_transferred": True,
            "audit_hash_match": True,
            "p99_ms": 150.0,
            "oscillation_detected": False,
            "rollback_safe": True,
            "data_sync_lag_ms": 100.0,
        }, TRACE_ID)
        assert sm.chaos_state == ChaosState.VERIFY_INTEGRITY
        sm.transition_chaos(ChaosTransition.C_T8, {
            "data_integrity_verified": True,
            "lease_transferred": True,
            "audit_hash_match": True,
            "p99_ms": 150.0,
            "oscillation_detected": False,
            "rollback_safe": True,
            "data_sync_lag_ms": 100.0,
        }, TRACE_ID)
        assert sm.chaos_state == ChaosState.COMPLETED

    def test_chaos_cycle_rollback_on_integrity_fail(self) -> None:
        sm = ReadinessStateMachine()
        sm.transition_chaos(ChaosTransition.C_T1, {
            "health_score": 1.0, "error_rate_pct": 0.0,
            "is_already_degraded": False, "expected_recovery_sec": 30.0,
        }, TRACE_ID)
        sm.transition_chaos(ChaosTransition.C_T2, {}, TRACE_ID)
        sm.transition_chaos(ChaosTransition.C_T3, {
            "degradation_metric": 0.1,
            "recovery_time_remaining_sec": 60.0,
            "cascade_failure_detected": False,
            "severity_propagation_contained": True,
        }, TRACE_ID)
        sm.transition_chaos(ChaosTransition.C_T5, {
            "data_integrity_verified": False,
            "lease_transferred": True,
            "audit_hash_match": True,
            "p99_ms": 150.0,
            "oscillation_detected": False,
            "rollback_safe": True,
            "data_sync_lag_ms": 100.0,
        }, TRACE_ID)
        assert sm.chaos_state == ChaosState.ROLLED_BACK

    def test_chaos_invalid_transition_returns_false(self) -> None:
        sm = ReadinessStateMachine()
        result = sm.transition_chaos(ChaosTransition.C_T8, {}, TRACE_ID)
        assert result["success"] is False
        assert "invalid_transition" in result["blocked_by"]


class TestCertificationGateTransitions:
    """Certification SM: Scoring and guards."""

    def test_certify_a_b_with_good_score(self) -> None:
        sm = ReadinessStateMachine()
        sm.transition_cert(CertificationGateTransition.G_T1, {}, TRACE_ID)
        sm.transition_cert(CertificationGateTransition.G_T2, {}, TRACE_ID)
        sm.transition_cert(CertificationGateTransition.G_T3, {}, TRACE_ID)
        result = sm.transition_cert(CertificationGateTransition.G_T4, {
            "final_score": 0.96,
            "data_integrity_verified": True,
            "p99_ms": 150.0,
            "oscillation_detected": False,
            "rollback_safe": True,
        }, TRACE_ID)
        assert result["to_state"] == "certified_a_b"

    def test_certify_c_with_moderate_score(self) -> None:
        sm = ReadinessStateMachine()
        sm.transition_cert(CertificationGateTransition.G_T1, {}, TRACE_ID)
        sm.transition_cert(CertificationGateTransition.G_T2, {}, TRACE_ID)
        sm.transition_cert(CertificationGateTransition.G_T3, {}, TRACE_ID)
        result = sm.transition_cert(CertificationGateTransition.G_T5, {
            "final_score": 0.80,
            "data_integrity_verified": True,
            "p99_ms": 150.0,
            "oscillation_detected": False,
            "rollback_safe": True,
        }, TRACE_ID)
        assert result["to_state"] == "certified_c"

    def test_block_on_p99_exceeded_during_cert(self) -> None:
        sm = ReadinessStateMachine()
        sm.transition_cert(CertificationGateTransition.G_T1, {}, TRACE_ID)
        sm.transition_cert(CertificationGateTransition.G_T2, {}, TRACE_ID)
        sm.transition_cert(CertificationGateTransition.G_T3, {}, TRACE_ID)
        result = sm.transition_cert(CertificationGateTransition.G_T4, {
            "final_score": 0.96,
            "data_integrity_verified": True,
            "p99_ms": 999.0,
            "oscillation_detected": False,
            "rollback_safe": True,
        }, TRACE_ID)
        assert result["to_state"] == "not_certified"

    def test_block_not_certified(self) -> None:
        sm = ReadinessStateMachine()
        sm.transition_cert(CertificationGateTransition.G_T1, {}, TRACE_ID)
        sm.transition_cert(CertificationGateTransition.G_T2, {}, TRACE_ID)
        sm.transition_cert(CertificationGateTransition.G_T3, {}, TRACE_ID)
        result = sm.transition_cert(CertificationGateTransition.G_T6, {}, TRACE_ID)
        assert result["to_state"] == "not_certified"

    def test_reset(self) -> None:
        sm = ReadinessStateMachine()
        sm.transition_cert(CertificationGateTransition.G_T1, {}, TRACE_ID)
        sm.reset()
        assert sm.cert_state == CertificationGateState.IDLE
        assert len(sm.transition_history) == 0
