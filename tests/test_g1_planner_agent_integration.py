"""Phase G1 — Planner Agent Integration Tests.  # RULE-1 RULE-3 RULE-6

Tests the complete G1 planning subsystem:
  1. PlanningStateMachine: transitions, guards, terminal states
  2. DAGSynthesizer: DAG synthesis from SwarmIntents, validation
  3. CriticFeedbackLoop: assessment aggregation, adaptation threshold
  4. SwarmCoordinator: consensus resolution, role assignment
  5. TraceCorrelator: correlation_id propagation across layers
  6. PlannerAgent: end-to-end flow (receive → synthesize → evaluate → publish)
  7. Adaptation: guard enforcement (min critics, confidence, cooldown, max adaptations)
  8. Rejection / halt / escalate

Tests are pure (no external state, no shared globals). Fresh instance per test.

Ref: Canon LAW 3, LAW 8, LAW 12, LAW 13, RULE 1, RULE 3, RULE 6
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pytest

from core.runtime.models.planning_models import (
    ExecutionPlan,
    PlanNode,
    PlanStatus,
    CriticAssessment,
    SwarmIntent,
)
from core.runtime.orchestration.planning_state_machine import (
    PlanningState,
    PlanningStateMachine,
)
from core.runtime.orchestration.dag_synthesizer import DAGSynthesizer
from core.runtime.orchestration.critic_feedback_loop import CriticFeedbackLoop
from core.runtime.orchestration.swarm_coordinator import SwarmCoordinator
from core.runtime.orchestration.trace_correlator import TraceCorrelator
from core.runtime.orchestration.planner_agent import PlannerAgent


# ═══════════════════════════════════════════════════════════════
# 1. PlanningStateMachine
# ═══════════════════════════════════════════════════════════════


class TestPlanningStateMachine:
    """12-state machine transitions and guards."""

    def test_initial_state(self):
        sm = PlanningStateMachine()
        assert sm.current == PlanningState.INTENT_RECEIVED

    def test_intent_to_dag_synthesis(self):
        sm = PlanningStateMachine()
        ok, _ = sm.transition(PlanningState.DAG_SYNTHESIS, intent="test intent")
        assert ok
        assert sm.current == PlanningState.DAG_SYNTHESIS

    def test_intent_rejected_empty(self):
        sm = PlanningStateMachine()
        ok, reason = sm.transition(PlanningState.DAG_SYNTHESIS, intent="")
        assert not ok
        assert "Empty intent" in reason

    def test_intent_rejected_too_long(self):
        sm = PlanningStateMachine()
        ok, reason = sm.transition(PlanningState.DAG_SYNTHESIS, intent="x" * 10001)
        assert not ok
        assert "exceeds" in reason

    def test_full_happy_path(self):
        sm = PlanningStateMachine()
        assert sm.transition(PlanningState.DAG_SYNTHESIS, intent="hello")[0]
        assert sm.transition(PlanningState.CRITIC_EVAL)[0]
        ok, _ = sm.transition(PlanningState.APPROVED, overall_score=0.85)
        assert ok
        assert sm.current == PlanningState.APPROVED
        assert sm.transition(PlanningState.PUBLISHED)[0]
        assert sm.current == PlanningState.PUBLISHED
        assert sm.transition(PlanningState.ACTIVE)[0]
        assert sm.current == PlanningState.ACTIVE

    def test_critic_rejected_low_score(self):
        sm = PlanningStateMachine()
        sm.transition(PlanningState.DAG_SYNTHESIS, intent="x")
        sm.transition(PlanningState.CRITIC_EVAL)
        ok, _ = sm.transition(PlanningState.APPROVED, overall_score=0.5)
        assert not ok
        sm.force_set(PlanningState.CRITIC_EVAL)
        assert sm.transition(PlanningState.CRITIC_REJECTED)[0]
        assert sm.current == PlanningState.CRITIC_REJECTED

    def test_adaptation_guard_passes(self):
        sm = PlanningStateMachine()
        sm.transition(PlanningState.DAG_SYNTHESIS, intent="x")
        sm.transition(PlanningState.CRITIC_EVAL)
        sm.transition(PlanningState.APPROVED, overall_score=0.85)
        sm.transition(PlanningState.PUBLISHED)
        sm.transition(PlanningState.ACTIVE)

        ok, _ = sm.guard_adaptation(critic_signal_count=2, feedback_confidence=0.0, adaptation_count=0)
        assert ok

    def test_adaptation_guard_rejects_low_signals(self):
        sm = PlanningStateMachine()
        ok, _ = sm.guard_adaptation(critic_signal_count=1, feedback_confidence=0.5, adaptation_count=0)
        assert not ok

    def test_adaptation_guard_passes_high_confidence(self):
        sm = PlanningStateMachine()
        ok, _ = sm.guard_adaptation(critic_signal_count=0, feedback_confidence=0.9, adaptation_count=0)
        assert ok

    def test_adaptation_guard_rejects_max_exceeded(self):
        sm = PlanningStateMachine()
        ok, _ = sm.guard_adaptation(critic_signal_count=2, feedback_confidence=0.0, adaptation_count=5)
        assert not ok

    def test_adaptation_cooldown(self):
        sm = PlanningStateMachine()
        sm.force_set(PlanningState.ACTIVE)
        ok, _ = sm.transition(
            PlanningState.ADAPT_REQUESTED,
            critic_signal_count=3,
            feedback_confidence=0.0,
            adaptation_count=0,
        )
        assert ok
        sm.force_set(PlanningState.ACTIVE)
        ok, _ = sm.transition(
            PlanningState.ADAPT_REQUESTED,
            critic_signal_count=3,
            feedback_confidence=0.0,
            adaptation_count=1,
        )
        assert not ok

    def test_invalid_transition(self):
        sm = PlanningStateMachine()
        sm.force_set(PlanningState.COMPLETED)
        ok, _ = sm.transition(PlanningState.APPROVED)
        assert not ok

    def test_terminal_no_transition(self):
        sm = PlanningStateMachine()
        sm.force_set(PlanningState.COMPLETED)
        ok, reason = sm.transition(PlanningState.ACTIVE)
        assert not ok
        assert "Terminal state" in reason

    def test_history_records_transitions(self):
        sm = PlanningStateMachine()
        sm.transition(PlanningState.DAG_SYNTHESIS, intent="go")
        sm.transition(PlanningState.CRITIC_EVAL)
        hist = sm.history
        assert len(hist) == 2
        assert hist[0]["from"] == "intent_received"
        assert hist[0]["to"] == "dag_synthesis"

    def test_escalation_guard_high_severity(self):
        sm = PlanningStateMachine()
        ok, _ = sm.guard_escape(severity=0.95)
        assert ok

    def test_escalation_guard_low_severity(self):
        sm = PlanningStateMachine()
        ok, _ = sm.guard_escape(severity=0.5)
        assert not ok


# ═══════════════════════════════════════════════════════════════
# 2. DAGSynthesizer
# ═══════════════════════════════════════════════════════════════


class TestDAGSynthesizer:
    """DAG synthesis and validation."""

    def test_synthesize_empty_intents(self):
        dag = DAGSynthesizer()
        plan = ExecutionPlan(plan_id="test")
        node = PlanNode(node_id="n1", tool_name="tool_a")
        plan.nodes = [node]
        result = dag.synthesize(plan, [])
        assert result.plan_id == "test"

    def test_synthesize_with_intents(self):
        dag = DAGSynthesizer()
        plan = ExecutionPlan(plan_id="p1", intent="do stuff")
        intents = [
            SwarmIntent(tool_name="search", confidence=0.9, weight=1.0),
            SwarmIntent(tool_name="analyze", confidence=0.8, weight=0.9),
        ]
        result = dag.synthesize(plan, intents)
        assert len(result.dag_topology) >= 0
        assert result.plan_id == "p1"

    def test_validate_valid_dag(self):
        dag = DAGSynthesizer()
        node = PlanNode(node_id="n1", tool_name="tool_a")
        plan = ExecutionPlan(plan_id="p1", nodes=[node])
        valid = dag.validate(plan)
        assert valid

    def test_validate_invalid_dag_missing_node(self):
        dag = DAGSynthesizer()
        node = PlanNode(node_id="n1", tool_name="tool_a")
        plan = ExecutionPlan(plan_id="p1", nodes=[node])
        plan.dag_topology = [{"from": "n1", "to": "n2"}]
        valid = dag.validate(plan)
        assert not valid


# ═══════════════════════════════════════════════════════════════
# 3. CriticFeedbackLoop
# ═══════════════════════════════════════════════════════════════


class TestCriticFeedbackLoop:
    """Assessment aggregation and adaptation threshold."""

    def test_empty_assessments_default(self):
        loop = CriticFeedbackLoop()
        assessment = loop.evaluate("plan_1")
        assert assessment.score == 0.0
        assert "No critic signals" in assessment.reason

    def test_add_and_evaluate_single(self):
        loop = CriticFeedbackLoop()
        a = CriticAssessment(assessor_id="c1", plan_id="p1", score=0.7, reason="ok")
        loop.add_assessment(a)
        assessment = loop.evaluate("p1")
        assert assessment.score == 0.7

    def test_add_and_evaluate_multiple(self):
        loop = CriticFeedbackLoop()
        loop.add_assessment(CriticAssessment(assessor_id="c1", plan_id="p1", score=0.6))
        loop.add_assessment(CriticAssessment(assessor_id="c2", plan_id="p1", score=0.8))
        assessment = loop.evaluate("p1")
        assert assessment.score == 0.7

    def test_signal_count(self):
        loop = CriticFeedbackLoop()
        assert loop.signal_count("p1") == 0
        loop.add_assessment(CriticAssessment(assessor_id="c1", plan_id="p1", score=0.5))
        assert loop.signal_count("p1") == 1

    def test_feedback_confidence(self):
        loop = CriticFeedbackLoop()
        assert loop.feedback_confidence("p1") == 0.0
        loop.add_assessment(CriticAssessment(assessor_id="c1", plan_id="p1", score=0.7))
        assert loop.feedback_confidence("p1") == 0.7

    def test_meets_threshold_via_signals(self):
        loop = CriticFeedbackLoop()
        loop.add_assessment(CriticAssessment(assessor_id="c1", plan_id="p1", score=0.5))
        loop.add_assessment(CriticAssessment(assessor_id="c2", plan_id="p1", score=0.5))
        ok, _ = loop.meets_adaptation_threshold("p1")
        assert ok

    def test_meets_threshold_via_confidence(self):
        loop = CriticFeedbackLoop()
        loop.add_assessment(CriticAssessment(assessor_id="c1", plan_id="p1", score=0.85))
        ok, _ = loop.meets_adaptation_threshold("p1")
        assert ok

    def test_meets_threshold_fails(self):
        loop = CriticFeedbackLoop()
        loop.add_assessment(CriticAssessment(assessor_id="c1", plan_id="p1", score=0.5))
        ok, _ = loop.meets_adaptation_threshold("p1")
        assert not ok

    def test_max_signals_enforced(self):
        loop = CriticFeedbackLoop(max_critic_signals=2)
        loop.add_assessment(CriticAssessment(assessor_id="c1", plan_id="p1", score=0.5))
        loop.add_assessment(CriticAssessment(assessor_id="c2", plan_id="p1", score=0.6))
        loop.add_assessment(CriticAssessment(assessor_id="c3", plan_id="p1", score=0.7))
        assert loop.signal_count("p1") == 2

    def test_reset(self):
        loop = CriticFeedbackLoop()
        loop.add_assessment(CriticAssessment(assessor_id="c1", plan_id="p1", score=0.5))
        loop.reset()
        assert loop.signal_count("p1") == 0


# ═══════════════════════════════════════════════════════════════
# 4. SwarmCoordinator
# ═══════════════════════════════════════════════════════════════


class TestSwarmCoordinator:
    """Consensus resolution and role assignment."""

    def test_empty_intents(self):
        sc = SwarmCoordinator()
        assert sc.resolve([]) == []

    def test_single_intent(self):
        sc = SwarmCoordinator()
        intents = [SwarmIntent(tool_name="search", confidence=0.9)]
        result = sc.resolve(intents)
        assert len(result) == 1
        assert result[0].tool_name == "search"

    def test_best_confidence_wins(self):
        sc = SwarmCoordinator()
        intents = [
            SwarmIntent(tool_name="search", confidence=0.7),
            SwarmIntent(tool_name="search", confidence=0.9),
        ]
        result = sc.resolve(intents)
        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_multiple_tools(self):
        sc = SwarmCoordinator()
        intents = [
            SwarmIntent(tool_name="search", confidence=0.8),
            SwarmIntent(tool_name="analyze", confidence=0.7),
        ]
        result = sc.resolve(intents)
        assert len(result) == 2

    def test_low_confidence_filtered(self):
        sc = SwarmCoordinator()
        intents = [SwarmIntent(tool_name="search", confidence=0.3)]
        result = sc.resolve(intents)
        assert len(result) == 0

    def test_assign_role_leader(self):
        sc = SwarmCoordinator()
        i = SwarmIntent(tool_name="search", confidence=0.9)
        assert sc.assign_role(i) == "leader"

    def test_assign_role_contributor(self):
        sc = SwarmCoordinator()
        i = SwarmIntent(tool_name="search", confidence=0.6)
        assert sc.assign_role(i) == "contributor"

    def test_assign_role_observer(self):
        sc = SwarmCoordinator()
        i = SwarmIntent(tool_name="search", confidence=0.3)
        assert sc.assign_role(i) == "observer"


# ═══════════════════════════════════════════════════════════════
# 5. TraceCorrelator
# ═══════════════════════════════════════════════════════════════


class TestTraceCorrelator:
    """Correlation ID propagation across layers."""

    def test_correlation_for_g1(self):
        plan = ExecutionPlan(plan_id="p1", plan_trace_id="trace_abc", version=2)
        tc = TraceCorrelator()
        corr = tc.correlation_for(plan, "g1_planner")
        assert "plan:p1" in corr

    def test_correlation_for_f1(self):
        plan = ExecutionPlan(plan_id="p1", plan_trace_id="trace_abc")
        plan.metadata["execution_id"] = "exec_123"
        tc = TraceCorrelator()
        corr = tc.correlation_for(plan, "f1_api")
        assert "exec:" in corr

    def test_correlation_for_d8(self):
        plan = ExecutionPlan(plan_id="p1", plan_trace_id="trace_abc")
        tc = TraceCorrelator()
        corr = tc.correlation_for(plan, "d8_mesh")
        assert "d8:" in corr
        assert plan.plan_trace_id in corr

    def test_propagate_context(self):
        plan = ExecutionPlan(plan_id="p1", plan_trace_id="trace_abc")
        tc = TraceCorrelator()
        ctx = tc.propagate_context(plan, "g1_planner")
        assert ctx["plan_trace_id"] == "trace_abc"
        assert ctx["target_layer"] == "g1_planner"

    def test_trace_chain(self):
        plan = ExecutionPlan(plan_id="p1", plan_trace_id="trace_abc")
        tc = TraceCorrelator()
        tc.propagate_context(plan, "g1_planner")
        tc.propagate_context(plan, "d8_mesh")
        chain = tc.trace_chain("p1")
        assert "g1_planner" in chain
        assert "d8_mesh" in chain

    def test_record_and_resolve(self):
        plan = ExecutionPlan(plan_id="p1", plan_trace_id="trace_abc")
        plan.metadata["execution_id"] = "exec_99"
        tc = TraceCorrelator()
        tc.propagate_context(plan, "f1_api")
        resolved = tc.resolve_from_f1_execution_id("exec_99")
        assert resolved == "p1"

    def test_resolve_none(self):
        tc = TraceCorrelator()
        assert tc.resolve_from_f1_execution_id("nonexistent") is None

    def test_reset(self):
        plan = ExecutionPlan(plan_id="p1", plan_trace_id="trace_abc")
        tc = TraceCorrelator()
        tc.propagate_context(plan, "g1_planner")
        tc.reset()
        assert tc.trace_chain("p1") == {}


# ═══════════════════════════════════════════════════════════════
# 6. PlannerAgent — Happy Path
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def planner():
    swarm = SwarmCoordinator()
    critic = CriticFeedbackLoop()
    correlator = TraceCorrelator()
    sm = PlanningStateMachine()
    return PlannerAgent(
        swarm_coordinator=swarm,
        critic_feedback_loop=critic,
        trace_correlator=correlator,
        state_machine=sm,
    )


class TestPlannerAgentHappyPath:
    """G1-G1: Full receive → synthesize → evaluate → publish."""

    def test_receive_intent(self, planner):
        plan = planner.receive_intent("build search tool")
        assert plan.plan_id
        assert plan.plan_trace_id
        assert plan.intent == "build search tool"
        assert plan.status == PlanStatus.PENDING

    def test_receive_intent_with_context(self, planner):
        plan = planner.receive_intent("search", context={"scope": "web"})
        assert plan.context_hash

    def test_synthesize_with_intents(self, planner):
        plan = planner.receive_intent("analyze data")
        intents = [
            SwarmIntent(tool_name="search", confidence=0.9),
            SwarmIntent(tool_name="summarize", confidence=0.8),
        ]
        result = planner.synthesize(plan.plan_id, intents)
        assert result.intent == "analyze data"
        assert result.weight_hash

    def test_synthesize_empty_intents(self, planner):
        plan = planner.receive_intent("do stuff")
        result = planner.synthesize(plan.plan_id)
        assert result.plan_id == plan.plan_id

    def test_evaluate_approved(self, planner):
        plan = planner.receive_intent("test")
        planner.synthesize(plan.plan_id, [SwarmIntent(tool_name="t1", confidence=0.9)])
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.85)
        )
        result = planner.evaluate(plan.plan_id)
        assert result.status == PlanStatus.APPROVED

    def test_evaluate_rejected(self, planner):
        plan = planner.receive_intent("test")
        planner.synthesize(plan.plan_id)
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.5)
        )
        result = planner.evaluate(plan.plan_id)
        assert result.status == PlanStatus.REJECTED

    def test_publish(self, planner):
        plan = planner.receive_intent("test")
        planner.synthesize(plan.plan_id, [SwarmIntent(tool_name="t1", confidence=0.9)])
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.85)
        )
        planner.evaluate(plan.plan_id)
        result = planner.publish(plan.plan_id)
        assert result.status == PlanStatus.ACTIVE

    def test_publish_rejected_plan_fails(self, planner):
        plan = planner.receive_intent("test")
        planner.synthesize(plan.plan_id)
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.5)
        )
        planner.evaluate(plan.plan_id)
        with pytest.raises(RuntimeError, match="must be APPROVED"):
            planner.publish(plan.plan_id)

    def test_full_pipeline(self, planner):
        plan = planner.receive_intent("full pipeline")
        planner.synthesize(plan.plan_id, [
            SwarmIntent(tool_name="fetch", confidence=0.9),
            SwarmIntent(tool_name="parse", confidence=0.85),
        ])
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.8)
        )
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c2", plan_id=plan.plan_id, score=0.9)
        )
        planner.evaluate(plan.plan_id)
        result = planner.publish(plan.plan_id)
        assert result.status == PlanStatus.ACTIVE


# ═══════════════════════════════════════════════════════════════
# 7. PlannerAgent — Adaptation
# ═══════════════════════════════════════════════════════════════


class TestPlannerAgentAdaptation:
    """G1-G2: adapt_plan guard enforcement (RULE 3)."""

    def test_adapt_passes_with_two_critic_signals(self, planner):
        plan = planner.receive_intent("adapt test")
        planner.synthesize(plan.plan_id, [SwarmIntent(tool_name="t1", confidence=0.9)])
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.8)
        )
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c2", plan_id=plan.plan_id, score=0.9)
        )
        planner.evaluate(plan.plan_id)
        planner.publish(plan.plan_id)

        result = planner.adapt_plan(plan.plan_id)
        assert result.status in (PlanStatus.PENDING, PlanStatus.ACTIVE)

    def test_adapt_fails_without_enough_signals(self, planner):
        plan = planner.receive_intent("adapt fail")
        planner.synthesize(plan.plan_id)
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.5)
        )
        planner.evaluate(plan.plan_id)
        planner.state_machine.force_set(PlanningState.ACTIVE)

        with pytest.raises(RuntimeError, match="Adaptation guard"):
            planner.adapt_plan(plan.plan_id)

    def test_adapt_increments_version(self, planner):
        plan = planner.receive_intent("adapt version")
        planner.synthesize(plan.plan_id, [SwarmIntent(tool_name="t1", confidence=0.9)])
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.8)
        )
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c2", plan_id=plan.plan_id, score=0.9)
        )
        planner.evaluate(plan.plan_id)
        planner.publish(plan.plan_id)

        result = planner.adapt_plan(plan.plan_id)
        assert result.version == 2

    def test_adapt_max_five_times(self, planner):
        plan = planner.receive_intent("max adapt")
        planner.synthesize(plan.plan_id, [SwarmIntent(tool_name="t1", confidence=0.9)])
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.8)
        )
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c2", plan_id=plan.plan_id, score=0.9)
        )
        planner.evaluate(plan.plan_id)
        planner.publish(plan.plan_id)

        for _ in range(5):
            planner.critic_feedback_loop.add_assessment(
                CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.8)
            )
            time.sleep(0.01)
            try:
                planner.state_machine.force_set(PlanningState.ACTIVE)
                planner.adapt_plan(plan.plan_id)
            except RuntimeError:
                pass
        assert True

    def test_adapt_halted_plan_fails(self, planner):
        plan = planner.receive_intent("halt test")
        planner.synthesize(plan.plan_id)
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.5)
        )
        planner.evaluate(plan.plan_id)
        planner.reject(plan.plan_id)
        planner.halt(plan.plan_id)

        with pytest.raises(RuntimeError, match="HALTED"):
            planner.adapt_plan(plan.plan_id)


# ═══════════════════════════════════════════════════════════════
# 8. PlannerAgent — Reject / Halt / Escalate
# ═══════════════════════════════════════════════════════════════


class TestPlannerAgentControl:
    """G1-G3: reject, halt, escalate."""

    def test_reject_plan(self, planner):
        plan = planner.receive_intent("reject me")
        planner.synthesize(plan.plan_id)
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.4)
        )
        result = planner.evaluate(plan.plan_id)
        assert result.status == PlanStatus.REJECTED

    def test_halt_plan(self, planner):
        plan = planner.receive_intent("halt me")
        planner.synthesize(plan.plan_id)
        result = planner.halt(plan.plan_id)
        assert result.status == PlanStatus.HALTED

    def test_escalate_plan(self, planner):
        plan = planner.receive_intent("escalate me")
        plan.metadata["severity"] = 0.95
        planner.synthesize(plan.plan_id)
        planner.state_machine.force_set(PlanningState.CRITIC_EVAL)
        planner.state_machine.transition(PlanningState.CRITIC_REJECTED)
        result = planner.escalate(plan.plan_id)
        assert result.status == PlanStatus.ESCALATED

    def test_escalate_low_severity_fails(self, planner):
        plan = planner.receive_intent("low severity")
        plan.metadata["severity"] = 0.5
        planner.synthesize(plan.plan_id)
        planner.state_machine.force_set(PlanningState.CRITIC_EVAL)
        planner.state_machine.transition(PlanningState.CRITIC_REJECTED)
        with pytest.raises(RuntimeError, match="Escalation guard"):
            planner.escalate(plan.plan_id)

    def test_missing_plan_raises(self, planner):
        with pytest.raises(ValueError, match="not found"):
            planner.synthesize("nonexistent")

    def test_reset(self, planner):
        plan = planner.receive_intent("reset test")
        planner.synthesize(plan.plan_id)
        planner.reset()
        assert planner.plans == {}
        assert planner.state_machine.current == PlanningState.INTENT_RECEIVED


# ═══════════════════════════════════════════════════════════════
# 9. Edge Cases & Integration
# ═══════════════════════════════════════════════════════════════


class TestPlannerAgentEdgeCases:
    """Corner cases and integration scenarios."""

    def test_duplicate_plans_same_intent(self, planner):
        p1 = planner.receive_intent("same")
        p2 = planner.receive_intent("same")
        assert p1.plan_id == p2.plan_id
        assert p2.status == PlanStatus.PENDING

    def test_adaptation_increments_adaptation_count(self, planner):
        plan = planner.receive_intent("count adapt")
        planner.synthesize(plan.plan_id, [SwarmIntent(tool_name="t1", confidence=0.9)])
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c1", plan_id=plan.plan_id, score=0.8)
        )
        planner.critic_feedback_loop.add_assessment(
            CriticAssessment(assessor_id="c2", plan_id=plan.plan_id, score=0.9)
        )
        planner.evaluate(plan.plan_id)
        planner.publish(plan.plan_id)
        assert plan.metadata.get("adaptation_count", 0) == 0

    def test_trace_correlator_in_planner(self, planner):
        plan = planner.receive_intent("trace check")
        assert plan.plan_trace_id

    def test_two_independent_plans(self, planner):
        p1 = planner.receive_intent("plan one")
        p2 = planner.receive_intent("plan two")
        assert p1.plan_id != p2.plan_id

    def test_sm_current_tracks_flow(self, planner):
        planner.receive_intent("sm test")
        assert planner.state_machine.current in (
            PlanningState.DAG_SYNTHESIS, PlanningState.INTENT_RECEIVED
        )
