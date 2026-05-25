"""Phase G3 — Optimization State Machine Patch Guard Tests.  # RULE-3

Tests the 6-state optimization SM with all guards, particularly the
3 Safe Patch Guards (cost_reduction ≥5% OR latency_improvement ≥10%,
rollback_plan != None, dag_integrity_check = true).

Ref: Canon RULE 3, LAW 14, LAW 15
Ref: artifacts/design/g3/03_optimization_state_machine.md
"""

from __future__ import annotations

import pytest

from core.runtime.models.optimizer_models import (
    OptimizationGuardReason,
    OptimizationProposal,
    PatchOperation,
)
from core.runtime.optimizer.optimization_state_machine import (
    OptimizationState,
    OptimizationStateMachine,
)


class TestOptimizationStateMachine:
    """6-state machine transitions and safe patch guards."""

    def test_initial_state(self):
        sm = OptimizationStateMachine()
        assert sm.current == OptimizationState.PLAN_RECEIVED

    def test_happy_path_to_approve(self):
        sm = OptimizationStateMachine()
        sm.transition(OptimizationState.TOPOLOGY_EVAL, nodes=[{"node_id": "n1"}], dag=[{"from": "n1", "to": "n2"}])
        sm.transition(OptimizationState.COST_LOAD_ANALYSIS, integrity_ok=True)
        ok, _ = sm.transition(OptimizationState.APPROVE, cost_efficiency=0.96, load_balance_score=0.96)
        assert ok
        assert sm.current == OptimizationState.APPROVE

    def test_happy_path_to_propose_patch(self):
        sm = OptimizationStateMachine()
        sm.transition(OptimizationState.TOPOLOGY_EVAL, nodes=[{"node_id": "n1"}], dag=[{"from": "n1", "to": "n2"}])
        sm.transition(OptimizationState.COST_LOAD_ANALYSIS, integrity_ok=True)
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-8.0,
            latency_impact_pct=-12.0,
            rollback_plan={"revert": "x"},
            dag_integrity_check=True,
        )
        ok, _ = sm.transition(OptimizationState.PROPOSE_PATCH, proposal=proposal)
        assert ok
        assert sm.current == OptimizationState.PROPOSE_PATCH

    def test_plan_received_no_nodes_rejected(self):
        sm = OptimizationStateMachine()
        ok, _ = sm.transition(OptimizationState.TOPOLOGY_EVAL, nodes=None, dag=None)
        assert not ok

    def test_dag_integrity_fail_rejected(self):
        sm = OptimizationStateMachine()
        sm.transition(OptimizationState.TOPOLOGY_EVAL, nodes=[{"node_id": "n1"}], dag=[{"from": "n1", "to": "n2"}])
        ok, _ = sm.transition(OptimizationState.COST_LOAD_ANALYSIS, integrity_ok=False)
        assert not ok
        assert sm.current == OptimizationState.TOPOLOGY_EVAL

    def test_safe_patch_guard_cost_too_low(self):
        sm = OptimizationStateMachine()
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-2.0,
            latency_impact_pct=-3.0,
            rollback_plan={"revert": "x"},
            dag_integrity_check=True,
        )
        ok, _ = sm.guard_safe_patch(proposal=proposal)
        assert not ok

    def test_safe_patch_guard_missing_rollback(self):
        sm = OptimizationStateMachine()
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-8.0,
            latency_impact_pct=-12.0,
            rollback_plan=None,
            dag_integrity_check=True,
        )
        ok, _ = sm.guard_safe_patch(proposal=proposal)
        assert not ok

    def test_safe_patch_guard_integrity_fail(self):
        sm = OptimizationStateMachine()
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-8.0,
            latency_impact_pct=-12.0,
            rollback_plan={"revert": "x"},
            dag_integrity_check=False,
        )
        ok, _ = sm.guard_safe_patch(proposal=proposal)
        assert not ok

    def test_safe_patch_guard_passes(self):
        sm = OptimizationStateMachine()
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-8.0,
            latency_impact_pct=-12.0,
            rollback_plan={"revert": "x"},
            dag_integrity_check=True,
        )
        ok, _ = sm.guard_safe_patch(proposal=proposal)
        assert ok

    def test_max_patches_enforced(self):
        sm = OptimizationStateMachine()
        sm._patch_count = 3
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-10.0,
            latency_impact_pct=-15.0,
            rollback_plan={"revert": "x"},
            dag_integrity_check=True,
        )
        ok, _ = sm.guard_safe_patch(proposal=proposal)
        assert not ok

    def test_defer_low_confidence(self):
        sm = OptimizationStateMachine()
        ok, _ = sm.guard_defer(confidence=0.5)
        assert ok

    def test_reject_budget_exceeded(self):
        sm = OptimizationStateMachine()
        ok, _ = sm.guard_reject(budget_exceeded=True, critical_imbalance=False)
        assert ok

    def test_no_opt_needed_passes(self):
        sm = OptimizationStateMachine()
        ok, _ = sm.guard_no_optimization_needed(cost_efficiency=0.96, load_balance_score=0.96)
        assert ok

    def test_no_opt_needed_fails(self):
        sm = OptimizationStateMachine()
        ok, _ = sm.guard_no_optimization_needed(cost_efficiency=0.7, load_balance_score=0.7)
        assert not ok

    def test_invalid_transition(self):
        sm = OptimizationStateMachine()
        ok, _ = sm.transition(OptimizationState.APPROVE)
        assert not ok

    def test_terminal_no_transitions(self):
        sm = OptimizationStateMachine()
        sm.force_set(OptimizationState.APPROVE)
        ok, _ = sm.transition(OptimizationState.REJECT)
        assert not ok


class TestSafePatchGuardEvaluation:
    """evaluate_safe_patch_guards — RULE 3 enforcement."""

    def test_all_guards_pass(self):
        sm = OptimizationStateMachine()
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-8.0,
            latency_impact_pct=-12.0,
            rollback_plan={"revert": "x"},
            dag_integrity_check=True,
        )
        result = sm.evaluate_safe_patch_guards(proposal)
        assert result.allowed

    def test_fails_cost_and_latency_too_low(self):
        sm = OptimizationStateMachine()
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-2.0,
            latency_impact_pct=-3.0,
            rollback_plan={"revert": "x"},
            dag_integrity_check=True,
        )
        result = sm.evaluate_safe_patch_guards(proposal)
        assert not result.allowed
        assert result.failed_guard == OptimizationGuardReason.INSUFFICIENT_COST_REDUCTION

    def test_fails_missing_rollback(self):
        sm = OptimizationStateMachine()
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-8.0,
            latency_impact_pct=-12.0,
            rollback_plan=None,
            dag_integrity_check=True,
        )
        result = sm.evaluate_safe_patch_guards(proposal)
        assert not result.allowed
        assert result.failed_guard == OptimizationGuardReason.MISSING_ROLLBACK_PLAN

    def test_fails_integrity_check(self):
        sm = OptimizationStateMachine()
        proposal = OptimizationProposal(
            estimated_cost_delta_pct=-8.0,
            latency_impact_pct=-12.0,
            rollback_plan={"revert": "x"},
            dag_integrity_check=False,
        )
        result = sm.evaluate_safe_patch_guards(proposal)
        assert not result.allowed
        assert result.failed_guard == OptimizationGuardReason.DAG_INTEGRITY_FAILED

    def test_determinism_hash_stable(self):
        sm = OptimizationStateMachine()
        h1 = sm.compute_determinism_hash({"a": 1}, {"b": 2}, {"c": 3})
        h2 = sm.compute_determinism_hash({"a": 1}, {"b": 2}, {"c": 3})
        assert h1 == h2

    def test_determinism_hash_different(self):
        sm = OptimizationStateMachine()
        h1 = sm.compute_determinism_hash({"a": 1}, {"b": 2}, {"c": 3})
        h2 = sm.compute_determinism_hash({"a": 1}, {"b": 99}, {"c": 3})
        assert h1 != h2
