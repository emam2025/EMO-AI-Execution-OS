"""Phase G3 — Optimization State Machine.  # LAW-14 LAW-15 RULE-1 RULE-3

6-state machine governing the G3 optimization lifecycle:
  PLAN_RECEIVED → TOPOLOGY_EVAL → COST_LOAD_ANALYSIS
    → [APPROVE / PROPOSE_PATCH / REJECT]
    → PROPOSE_PATCH → [DEFER | COST_LOAD_ANALYSIS]

Safe Patch Guards (RULE 3):
  - cost_reduction >= 5% OR latency_improvement >= 10%
  - rollback_plan != None
  - dag_integrity_check == true

Deterministic Optimization Guard (RULE 1):
  - Cache keyed by sha256(plan + metrics + cost_budget)
  - Same input → same proposals

Ref: Canon LAW 14, LAW 15, RULE 1, RULE 3, RULE 5
Ref: artifacts/design/g3/03_optimization_state_machine.md
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.models.optimizer_models import (
    OptimizationGuardReason,
    OptimizationProposal,
    SafePatchGuardResult,
)

logger = logging.getLogger("emo_ai.optimizer.optimization_sm")


class OptimizationState(str, Enum):  # LAW-14
    PLAN_RECEIVED = "plan_received"
    TOPOLOGY_EVAL = "topology_eval"
    COST_LOAD_ANALYSIS = "cost_load_analysis"
    APPROVE = "approve"
    PROPOSE_PATCH = "propose_patch"
    REJECT = "reject"
    DEFER = "defer"


TERMINAL_STATES: set = {
    OptimizationState.APPROVE,
    OptimizationState.REJECT,
}

TRANSITIONS: Dict[Tuple[OptimizationState, OptimizationState], Optional[str]] = {
    (OptimizationState.PLAN_RECEIVED, OptimizationState.TOPOLOGY_EVAL): "guard_has_plan",
    (OptimizationState.TOPOLOGY_EVAL, OptimizationState.COST_LOAD_ANALYSIS): "guard_dag_integrity",
    (OptimizationState.TOPOLOGY_EVAL, OptimizationState.REJECT): "guard_dag_invalid",
    (OptimizationState.COST_LOAD_ANALYSIS, OptimizationState.APPROVE): "guard_no_optimization_needed",
    (OptimizationState.COST_LOAD_ANALYSIS, OptimizationState.PROPOSE_PATCH): "guard_safe_patch",
    (OptimizationState.COST_LOAD_ANALYSIS, OptimizationState.REJECT): "guard_reject",
    (OptimizationState.PROPOSE_PATCH, OptimizationState.DEFER): "guard_defer",
    (OptimizationState.PROPOSE_PATCH, OptimizationState.COST_LOAD_ANALYSIS): "guard_re_evaluate",
    (OptimizationState.DEFER, OptimizationState.COST_LOAD_ANALYSIS): "guard_retry",
}


class OptimizationStateMachine:  # LAW-14 LAW-15
    """6-state machine for the G3 optimization lifecycle.

    All transitions are guarded. Safe Patch Guards enforce RULE 3.
    Deterministic Optimization Guard ensures RULE 1 compliance.
    """

    COST_REDUCTION_THRESHOLD_PCT: float = 5.0
    LATENCY_IMPROVEMENT_THRESHOLD_PCT: float = 10.0
    MIN_CONFIDENCE_FOR_PATCH: float = 0.6
    RETRY_COOLDOWN_MS: float = 10000.0
    MAX_PATCHES_PER_PLAN: int = 3
    DETERMINISM_CACHE_TTL_S: float = 3600.0
    FAIRNESS_THRESHOLD: float = 0.2

    def __init__(self) -> None:
        self._current = OptimizationState.PLAN_RECEIVED
        self._history: List[Dict[str, Any]] = []
        self._error: Optional[str] = None
        self._patch_count: int = 0
        self._last_retry_time: float = 0.0
        self._determinism_cache: Dict[str, Tuple[float, Any]] = {}

    @property
    def current(self) -> OptimizationState:
        return self._current

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    @property
    def patch_count(self) -> int:
        return self._patch_count

    # ── Guards ──────────────────────────────────────────────────

    def guard_has_plan(  # LAW-14
        self,
        nodes: Optional[List[Dict[str, Any]]] = None,
        dag: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, str]:
        if not nodes:
            return False, "Empty nodes list"
        if not dag:
            return False, "Empty dag_topology"
        return True, ""

    def guard_dag_integrity(  # LAW-14
        self,
        integrity_ok: bool = False,
    ) -> Tuple[bool, str]:
        if integrity_ok:
            return True, ""
        return False, "DAG integrity check failed"

    def guard_dag_invalid(  # LAW-14
        self,
        integrity_ok: bool = True,
    ) -> Tuple[bool, str]:
        if not integrity_ok:
            return True, ""
        return False, "DAG integrity check passed — should not reject"

    def guard_no_optimization_needed(  # LAW-15
        self,
        cost_efficiency: float = 1.0,
        load_balance_score: float = 1.0,
    ) -> Tuple[bool, str]:
        if cost_efficiency >= 0.95 and load_balance_score >= 0.95:
            return True, ""
        return False, f"Cost eff {cost_efficiency:.2f} or load {load_balance_score:.2f} below threshold"

    def guard_safe_patch(  # RULE-3
        self,
        proposal: Optional[OptimizationProposal] = None,
    ) -> Tuple[bool, str]:
        if proposal is None:
            return False, "No proposal provided"

        if self._patch_count >= self.MAX_PATCHES_PER_PLAN:
            return False, f"Max {self.MAX_PATCHES_PER_PLAN} patches per plan exceeded"

        cost_ok = proposal.estimated_cost_delta_pct <= -self.COST_REDUCTION_THRESHOLD_PCT
        latency_ok = proposal.latency_impact_pct <= -self.LATENCY_IMPROVEMENT_THRESHOLD_PCT

        if not (cost_ok or latency_ok):
            cost_gap = proposal.estimated_cost_delta_pct + self.COST_REDUCTION_THRESHOLD_PCT
            lat_gap = proposal.latency_impact_pct + self.LATENCY_IMPROVEMENT_THRESHOLD_PCT
            return False, (
                f"Need cost_reduction >= {self.COST_REDUCTION_THRESHOLD_PCT}% "
                f"(got {proposal.estimated_cost_delta_pct:.1f}%) "
                f"OR latency_improvement >= {self.LATENCY_IMPROVEMENT_THRESHOLD_PCT}% "
                f"(got {proposal.latency_impact_pct:.1f}%)"
            )
        if proposal.rollback_plan is None:
            return False, "Missing rollback plan"
        if not proposal.dag_integrity_check:
            return False, "DAG integrity check failed"
        return True, ""

    def guard_reject(  # LAW-7
        self,
        budget_exceeded: bool = False,
        critical_imbalance: bool = False,
    ) -> Tuple[bool, str]:
        if budget_exceeded or critical_imbalance:
            return True, ""
        return False, "Neither budget exceeded nor critical imbalance"

    def guard_defer(  # RULE-5
        self,
        confidence: float = 0.0,
    ) -> Tuple[bool, str]:
        if confidence < self.MIN_CONFIDENCE_FOR_PATCH:
            return True, ""
        return False, f"Confidence {confidence:.2f} >= {self.MIN_CONFIDENCE_FOR_PATCH} — should not defer"

    def guard_re_evaluate(  # RULE-1
        self,
    ) -> Tuple[bool, str]:
        return True, ""

    def guard_retry(  # RULE-5
        self,
    ) -> Tuple[bool, str]:
        now_ms = time.time() * 1000
        elapsed = now_ms - self._last_retry_time
        if elapsed >= self.RETRY_COOLDOWN_MS:
            self._last_retry_time = now_ms
            return True, ""
        remaining = self.RETRY_COOLDOWN_MS - elapsed
        return False, f"Retry cooldown {remaining:.0f}ms remaining"

    # ── Safe Patch Guard Evaluation ─────────────────────────────

    def evaluate_safe_patch_guards(  # RULE-3
        self,
        proposal: OptimizationProposal,
    ) -> SafePatchGuardResult:
        cost_ok = proposal.estimated_cost_delta_pct <= -self.COST_REDUCTION_THRESHOLD_PCT
        latency_ok = proposal.latency_impact_pct <= -self.LATENCY_IMPROVEMENT_THRESHOLD_PCT
        has_rollback = proposal.rollback_plan is not None
        integrity = proposal.dag_integrity_check

        if self._patch_count >= self.MAX_PATCHES_PER_PLAN:
            return SafePatchGuardResult(
                allowed=False,
                reason=f"Max {self.MAX_PATCHES_PER_PLAN} patches per plan exceeded",
                failed_guard=OptimizationGuardReason.DAG_INTEGRITY_FAILED,
                cost_reduction_pct=proposal.estimated_cost_delta_pct,
                latency_improvement_pct=proposal.latency_impact_pct,
                has_rollback_plan=has_rollback,
                dag_integrity_check=integrity,
            )

        if not (cost_ok or latency_ok):
            return SafePatchGuardResult(
                allowed=False,
                reason=f"Need cost_reduction >= {self.COST_REDUCTION_THRESHOLD_PCT}% "
                       f"OR latency >= {self.LATENCY_IMPROVEMENT_THRESHOLD_PCT}%",
                failed_guard=OptimizationGuardReason.INSUFFICIENT_COST_REDUCTION,
                cost_reduction_pct=proposal.estimated_cost_delta_pct,
                latency_improvement_pct=proposal.latency_impact_pct,
                has_rollback_plan=has_rollback,
                dag_integrity_check=integrity,
            )

        if not has_rollback:
            return SafePatchGuardResult(
                allowed=False,
                reason="Missing rollback plan",
                failed_guard=OptimizationGuardReason.MISSING_ROLLBACK_PLAN,
                cost_reduction_pct=proposal.estimated_cost_delta_pct,
                latency_improvement_pct=proposal.latency_impact_pct,
                has_rollback_plan=has_rollback,
                dag_integrity_check=integrity,
            )

        if not integrity:
            return SafePatchGuardResult(
                allowed=False,
                reason="DAG integrity check failed",
                failed_guard=OptimizationGuardReason.DAG_INTEGRITY_FAILED,
                cost_reduction_pct=proposal.estimated_cost_delta_pct,
                latency_improvement_pct=proposal.latency_impact_pct,
                has_rollback_plan=has_rollback,
                dag_integrity_check=integrity,
            )

        return SafePatchGuardResult(
            allowed=True,
            reason="All guards passed",
            cost_reduction_pct=proposal.estimated_cost_delta_pct,
            latency_improvement_pct=proposal.latency_impact_pct,
            has_rollback_plan=has_rollback,
            dag_integrity_check=integrity,
        )

    # ── Deterministic Optimization Guard ────────────────────────

    def compute_determinism_hash(  # RULE-1
        self,
        plan: Dict[str, Any],
        metrics: Dict[str, Any],
        cost_budget: Dict[str, Any],
    ) -> str:
        raw = self._normalize(plan) + self._normalize(metrics) + self._normalize(cost_budget)
        return hashlib.sha256(raw.encode()).hexdigest()

    def check_deterministic_review(  # RULE-1
        self,
        plan: Dict[str, Any],
        metrics: Dict[str, Any],
        cost_budget: Dict[str, Any],
    ) -> Tuple[bool, Any]:
        cache_key = self.compute_determinism_hash(plan, metrics, cost_budget)
        now = time.time()

        if cache_key in self._determinism_cache:
            cached_time, cached_result = self._determinism_cache[cache_key]
            if now - cached_time < self.DETERMINISM_CACHE_TTL_S:
                return True, cached_result

        return False, None

    def cache_deterministic_review(  # RULE-1
        self,
        plan: Dict[str, Any],
        metrics: Dict[str, Any],
        cost_budget: Dict[str, Any],
        result: Any,
    ) -> str:
        cache_key = self.compute_determinism_hash(plan, metrics, cost_budget)
        self._determinism_cache[cache_key] = (time.time(), result)
        return cache_key

    # ── Transition ──────────────────────────────────────────────

    def transition(
        self,
        to_state: OptimizationState,
        **kwargs,
    ) -> Tuple[bool, str]:
        key = (self._current, to_state)

        if self._current in TERMINAL_STATES:
            return False, f"Terminal state {self._current.value} — no transitions"

        if key not in TRANSITIONS:
            return False, (
                f"Invalid transition: {self._current.value} → {to_state.value}"
            )

        guard_name = TRANSITIONS[key]
        if guard_name is None:
            self._apply(to_state)
            return True, ""

        guard_fn = getattr(self, guard_name, None)
        if guard_fn is None:
            return False, f"Guard {guard_name} not implemented"

        result = guard_fn(**kwargs)
        if isinstance(result, tuple):
            allowed, reason = result
        else:
            allowed, reason = bool(result), ""

        if allowed:
            self._apply(to_state)
            return True, reason
        return False, reason

    def force_set(self, state: OptimizationState) -> None:
        self._current = state

    def is_terminal(self) -> bool:
        return self._current in TERMINAL_STATES

    def can_patch(self) -> bool:
        return self._patch_count < self.MAX_PATCHES_PER_PLAN

    def reset(self) -> None:
        self._current = OptimizationState.PLAN_RECEIVED
        self._history.clear()
        self._error = None
        self._patch_count = 0
        self._last_retry_time = 0.0

    def _apply(self, to_state: OptimizationState) -> None:
        self._history.append({
            "from": self._current.value,
            "to": to_state.value,
        })
        if to_state == OptimizationState.PROPOSE_PATCH:
            self._patch_count += 1
        self._current = to_state

    @staticmethod
    def _normalize(obj: Any) -> str:
        return json.dumps(obj, sort_keys=True, default=str)
