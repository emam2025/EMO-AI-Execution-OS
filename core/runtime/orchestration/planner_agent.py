"""Phase G1 — PlannerAgent implementation.  # LAW-13 # RULE-3

Central orchestrator for the G1 subsystem. Accepts user intent,
invokes DAGSynthesizer + CriticFeedbackLoop + SwarmCoordinator,
and produces deterministically-replayable ExecutionPlans.

LAW 13: Constructed by CompositionRoot (singleton factory).
RULE 3: adapt_plan() requires ≥2 critic signals OR ≥0.8 confidence.
RULE 1: All plans are deterministically replayable.

Ref: Canon LAW 13 (UnifiedRuntime), RULE 1, RULE 3
Ref: artifacts/design/g1/01_protocols.md
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.models.planning_models import (
    ExecutionPlan,
    SwarmIntent,
    PlanNode,
    PlanStatus,
)

from core.runtime.orchestration.planning_state_machine import (
    PlanningState,
    PlanningStateMachine,
    TERMINAL_STATES,
)
from core.runtime.orchestration.dag_synthesizer import DAGSynthesizer
from core.runtime.orchestration.critic_feedback_loop import CriticFeedbackLoop
from core.runtime.orchestration.swarm_coordinator import SwarmCoordinator
from core.runtime.orchestration.trace_correlator import TraceCorrelator

logger = logging.getLogger("emo_ai.orchestration.planner_agent")

TraceContext = Dict[str, str]


class PlannerAgent:  # LAW-13
    """Central orchestrator for the G1 planning subsystem.

    Flow:
      1. receive_intent → ExecutionPlan created, SM → DAG_SYNTHESIS
      2. synthesize → DAGSynthesizer builds DAG, SM → CRITIC_EVAL
      3. evaluate → CriticFeedbackLoop scores plan, SM → APPROVED/REJECTED
      4. publish → plan marked as PUBLISHED/ACTIVE
      5. adapt (optional) → guarded by RULE 3, SM → CRITIC_EVAL
    """

    def __init__(
        self,
        swarm_coordinator: SwarmCoordinator,
        critic_feedback_loop: CriticFeedbackLoop,
        trace_correlator: TraceCorrelator,
        state_machine: PlanningStateMachine,
    ) -> None:
        self._swarm = swarm_coordinator
        self._critic = critic_feedback_loop
        self._correlator = trace_correlator
        self._sm = state_machine
        self._dag = DAGSynthesizer()
        self._plans: Dict[str, ExecutionPlan] = {}

    # ── Properties ──────────────────────────────────────────────

    @property
    def state_machine(self) -> PlanningStateMachine:
        return self._sm

    @property
    def critic_feedback_loop(self) -> CriticFeedbackLoop:
        return self._critic

    @property
    def swarm_coordinator(self) -> SwarmCoordinator:
        return self._swarm

    @property
    def trace_correlator(self) -> TraceCorrelator:
        return self._correlator

    @property
    def plans(self) -> Dict[str, ExecutionPlan]:
        return dict(self._plans)

    # ── receive_intent ──────────────────────────────────────────

    def receive_intent(  # RULE-1
        self,
        intent: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        ok, reason = self._sm.guard_intent(intent=intent)
        if not ok:
            raise RuntimeError(f"Guard blocked: receive_intent — {reason}")

        plan = ExecutionPlan(
            plan_id=self._compute_hash(intent),
            plan_trace_id=self._compute_trace_id(intent),
            intent=intent,
            context_hash=self._context_hash(context),
            dag_topology=[],
            status=PlanStatus.PENDING,
        )
        plan.metadata["created_at"] = time.time()
        plan.metadata["execution_id"] = plan.plan_trace_id[:12]
        self._plans[plan.plan_id] = plan

        self._transition(PlanningState.DAG_SYNTHESIS, intent=intent)
        return plan

    # ── synthesize ──────────────────────────────────────────────

    def synthesize(  # RULE-1
        self,
        plan_id: str,
        intents: Optional[List[SwarmIntent]] = None,
    ) -> ExecutionPlan:
        plan = self._get_plan(plan_id)

        if intents:
            resolved = self._swarm.resolve(intents)
        else:
            resolved = []

        plan = self._dag.synthesize(plan, resolved)
        plan.weight_hash = self._weight_hash(resolved)

        self._transition(PlanningState.VALIDATED)

        # Trace correlation
        self._correlator.propagate_context(plan, "g1_planner")
        self._correlator.propagate_context(plan, "d8_mesh")

        self._transition(PlanningState.CRITIC_EVAL)
        return plan

    # ── evaluate ────────────────────────────────────────────────

    def evaluate(  # LAW-8
        self,
        plan_id: str,
    ) -> ExecutionPlan:
        plan = self._get_plan(plan_id)
        assessment = self._critic.evaluate(plan_id)
        plan.confidence = assessment.score or 0.0

        result = self._sm.transition(
            PlanningState.APPROVED,
            overall_score=assessment.score or 0.0,
        )
        if result[0]:
            plan.status = PlanStatus.APPROVED
        else:
            self._sm.transition(PlanningState.CRITIC_REJECTED)
            plan.status = PlanStatus.REJECTED

        self._correlator.propagate_context(plan, "f4_observer")
        return plan

    # ── publish ─────────────────────────────────────────────────

    def publish(  # RULE-2
        self,
        plan_id: str,
    ) -> ExecutionPlan:
        plan = self._get_plan(plan_id)
        if plan.status != PlanStatus.APPROVED:
            raise RuntimeError(f"Plan {plan_id} status {plan.status} — must be APPROVED")

        result = self._sm.transition(PlanningState.PUBLISHED)

        if not result[0]:
            plan.status = PlanStatus.FAILED
            self._sm.transition(PlanningState.FAILED)
            return plan

        plan.status = PlanStatus.PUBLISHED
        plan.metadata["published_at"] = time.time()

        self._sm.transition(PlanningState.ACTIVE)
        plan.status = PlanStatus.ACTIVE
        return plan

    # ── adapt_plan ──────────────────────────────────────────────

    def adapt_plan(  # RULE-3
        self,
        plan_id: str,
        new_intents: Optional[List[SwarmIntent]] = None,
    ) -> ExecutionPlan:
        plan = self._get_plan(plan_id)
        if plan.status == PlanStatus.HALTED:
            raise RuntimeError(f"Plan {plan_id} is HALTED — cannot adapt")
        if self._sm.current in TERMINAL_STATES:
            raise RuntimeError(f"SM in terminal state {self._sm.current.value}")

        count = self._critic.signal_count(plan_id)
        confidence = self._critic.feedback_confidence(plan_id)
        adaptation_count = plan.metadata.get("adaptation_count", 0)

        ok, reason = self._sm.transition(
            PlanningState.ADAPT_REQUESTED,
            critic_signal_count=count,
            feedback_confidence=confidence,
            adaptation_count=adaptation_count,
        )
        if not ok:
            raise RuntimeError(f"Adaptation guard: {reason}")

        plan.metadata["adaptation_count"] = adaptation_count + 1
        plan.version += 1

        if new_intents:
            resolved = self._swarm.resolve(new_intents)
            plan = self._dag.synthesize(plan, resolved)

        self._sm.transition(PlanningState.CRITIC_EVAL)
        plan.status = PlanStatus.PENDING

        return plan

    # ── reject / halt / escalate ────────────────────────────────

    def reject(  # LAW-8
        self,
        plan_id: str,
    ) -> ExecutionPlan:
        plan = self._get_plan(plan_id)
        self._sm.transition(PlanningState.CRITIC_REJECTED)
        plan.status = PlanStatus.REJECTED
        return plan

    def halt(  # LAW-8
        self,
        plan_id: str,
    ) -> ExecutionPlan:
        plan = self._get_plan(plan_id)
        self._sm.transition(PlanningState.HALTED)
        plan.status = PlanStatus.HALTED
        return plan

    def escalate(  # LAW-8
        self,
        plan_id: str,
    ) -> ExecutionPlan:
        plan = self._get_plan(plan_id)
        result = self._sm.transition(
            PlanningState.ESCALATED,
            severity=plan.metadata.get("severity", 0.0),
        )
        if not result[0]:
            raise RuntimeError(f"Escalation guard: {result[1]}")
        plan.status = PlanStatus.ESCALATED
        return plan

    # ── Internal helpers ────────────────────────────────────────

    def _get_plan(self, plan_id: str) -> ExecutionPlan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise ValueError(f"Plan {plan_id} not found")
        return plan

    def _transition(self, state: PlanningState, **kwargs) -> bool:
        ok, _ = self._sm.transition(state, **kwargs)
        return ok

    def _compute_hash(self, intent: str) -> str:
        return hashlib.sha256(intent.encode()).hexdigest()[:16]

    def _compute_trace_id(self, intent: str) -> str:
        return f"trace_{hashlib.sha256(intent.encode()).hexdigest()[:20]}"

    def _context_hash(self, context: Optional[Dict]) -> str:
        if not context:
            return ""
        raw = "".join(f"{k}={v}" for k, v in sorted(context.items()))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _weight_hash(self, intents: List[SwarmIntent]) -> str:
        raw = "".join(
            f"{i.tool_name}={i.weight or 1.0}|{i.confidence or 0.0}"
            for i in sorted(intents, key=lambda x: x.tool_name or "")
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def reset(self) -> None:
        self._plans.clear()
        self._sm.force_set(PlanningState.INTENT_RECEIVED)
        self._critic.reset()
        self._correlator.reset()
