"""Unit tests for OrchestrationStateMachine guards (G-P1–G-P8)."""

from __future__ import annotations

import pytest

from core.orchestration.orchestration_state_machine import (
    OrchestrationStateMachine,
    OrchestrationState,
    OrchestrationTransition,
)


class TestOrchestrationStateMachineGuards:
    def test_g_t1_planning_to_criticizing(self) -> None:
        sm = OrchestrationStateMachine()
        r = sm.transition(OrchestrationTransition.G_T1, {"tenant_id": "ten_a"})
        assert r["status"] == "ok"
        assert sm.state == OrchestrationState.CRITICIZING

    def test_g_t2_approve_valid(self) -> None:
        sm = OrchestrationStateMachine()
        sm.transition(OrchestrationTransition.G_T1, {})
        r = sm.transition(OrchestrationTransition.G_T2, {
            "owning_tenant": "ten_a", "requested_tenant": "ten_a", "scope_verified": False,
        })
        assert r["status"] == "ok"
        assert sm.state == OrchestrationState.APPROVED

    def test_g_t2_blocks_cross_tenant_without_scope(self) -> None:
        sm = OrchestrationStateMachine()
        sm.transition(OrchestrationTransition.G_T1, {})
        r = sm.transition(OrchestrationTransition.G_T2, {
            "owning_tenant": "ten_a", "requested_tenant": "ten_b", "scope_verified": False,
        })
        assert r["status"] == "blocked"

    def test_g_t2_passes_cross_tenant_with_scope(self) -> None:
        sm = OrchestrationStateMachine()
        sm.transition(OrchestrationTransition.G_T1, {})
        r = sm.transition(OrchestrationTransition.G_T2, {
            "owning_tenant": "ten_a", "requested_tenant": "ten_b", "scope_verified": True,
        })
        assert r["status"] == "ok"

    def test_g_t3_reject_requires_reason(self) -> None:
        sm = OrchestrationStateMachine()
        sm.transition(OrchestrationTransition.G_T1, {})
        r = sm.transition(OrchestrationTransition.G_T3, {"rejection_reason": ""})
        assert r["status"] == "blocked"

    def test_g_t4_blocks_oscillation(self) -> None:
        sm = OrchestrationStateMachine()
        sm.transition(OrchestrationTransition.G_T1, {})
        sm.transition(OrchestrationTransition.G_T3, {"rejection_reason": "bad plan"})
        r = sm.transition(OrchestrationTransition.G_T4, {
            "original_hash": "abc123", "revised_hash": "abc123",
        })
        assert r["status"] == "blocked"

    def test_g_t4_passes_different_hash(self) -> None:
        sm = OrchestrationStateMachine()
        sm.transition(OrchestrationTransition.G_T1, {})
        sm.transition(OrchestrationTransition.G_T3, {"rejection_reason": "bad plan"})
        r = sm.transition(OrchestrationTransition.G_T4, {
            "original_hash": "abc123", "revised_hash": "def456",
        })
        assert r["status"] == "ok"
        assert sm.state == OrchestrationState.PLANNING

    def test_g_t5_aborts_on_max_retries(self) -> None:
        sm = OrchestrationStateMachine(max_retry=0)
        sm.transition(OrchestrationTransition.G_T1, {})
        sm.transition(OrchestrationTransition.G_T3, {"rejection_reason": "x"})
        r = sm.transition(OrchestrationTransition.G_T5, {})
        assert r["status"] == "ok"
        assert sm.state == OrchestrationState.ABORTED

    def test_g_t6_abort_from_planning(self) -> None:
        sm = OrchestrationStateMachine()
        r = sm.transition(OrchestrationTransition.G_T6, {})
        assert r["status"] == "ok"
        assert sm.state == OrchestrationState.ABORTED

    def test_full_lifecycle(self) -> None:
        sm = OrchestrationStateMachine()
        assert sm.state == OrchestrationState.PLANNING
        sm.transition(OrchestrationTransition.G_T1, {})
        assert sm.state == OrchestrationState.CRITICIZING
        sm.transition(OrchestrationTransition.G_T2, {})
        assert sm.state == OrchestrationState.APPROVED
        sm.transition(OrchestrationTransition.G_T7, {})
        assert sm.state == OrchestrationState.OPTIMIZING
        sm.transition(OrchestrationTransition.G_T8, {"submit_ok": True})
        assert sm.state == OrchestrationState.EXECUTING
        sm.transition(OrchestrationTransition.G_T9, {})
        assert sm.state == OrchestrationState.COMPLETED
