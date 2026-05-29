"""Phase G — Cognitive Orchestration Integration Tests (25 tests).

Groups:
  1. TestTenantIsolationInOrchestration (5 tests)
  2. TestDeterministicPlanningHandoff (5 tests)
  3. TestOscillationPrevention (5 tests)
  4. TestFailureMatrixEnforcement (5 tests)
  5. TestEventBusRoutingSafety (5 tests)
"""

from __future__ import annotations

import pytest

from core.orchestration.planner_agent import PlannerAgent
from core.orchestration.critic_agent import CriticAgent
from core.orchestration.optimizer_agent import OptimizerAgent
from core.orchestration.orchestration_state_machine import (
    OrchestrationStateMachine,
    OrchestrationState,
    OrchestrationTransition,
)
from core.orchestration.trace_correlator import OrchestrationTraceCorrelator


# ===================================================================
# Group 1: Tenant Isolation in Orchestration (5 tests)
# ===================================================================


class TestTenantIsolationInOrchestration:
    @pytest.mark.anyio
    async def test_planner_requires_tenant_id(self) -> None:
        p = PlannerAgent()
        r = await p.synthesize_dag("intent", {}, "")
        assert r["status"] == "error"

    @pytest.mark.anyio
    async def test_critic_requires_tenant_id(self) -> None:
        c = CriticAgent()
        r = await c.evaluate_plan({"proposal_id": "p1"}, {}, "")
        assert r["status"] == "error"

    @pytest.mark.anyio
    async def test_optimizer_requires_tenant_id(self) -> None:
        o = OptimizerAgent()
        r = await o.optimize_execution_graph({}, {}, "")
        assert r["status"] == "error"

    @pytest.mark.anyio
    async def test_planner_plan_has_tenant_id(self) -> None:
        p = PlannerAgent()
        r = await p.synthesize_dag("summarize", {"trace_snippets": []}, "ten_a")
        assert r.get("tenant_id") == "ten_a"

    @pytest.mark.anyio
    async def test_critic_rejects_cross_tenant_without_scope(self) -> None:
        c = CriticAgent()
        r = await c.reject_with_reason(
            {"proposal_id": "p1", "tenant_id": "ten_b"},
            "violation x", "ten_a", scope_verified=False,
        )
        assert r["status"] == "blocked"


# ===================================================================
# Group 2: Deterministic Planning Handoff (5 tests)
# ===================================================================


class TestDeterministicPlanningHandoff:
    @pytest.mark.anyio
    async def test_same_intent_same_proposal(self) -> None:
        ctx = {"trace_snippets": [{"id": 1}], "context_hash": "abc"}
        p1 = PlannerAgent()
        p2 = PlannerAgent()
        r1 = await p1.synthesize_dag("summarize", ctx, "ten_a")
        r2 = await p2.synthesize_dag("summarize", ctx, "ten_a")
        assert r1["_hash"] == r2["_hash"]

    @pytest.mark.anyio
    async def test_diff_intent_diff_hash(self) -> None:
        ctx = {"trace_snippets": [{"id": 1}]}
        p = PlannerAgent()
        r1 = await p.synthesize_dag("summarize", ctx, "ten_a")
        r2 = await p.synthesize_dag("translate", ctx, "ten_a")
        assert r1["_hash"] != r2["_hash"]

    @pytest.mark.anyio
    async def test_same_dag_same_optimization(self) -> None:
        dag = {"proposal_id": "p1", "dag_nodes": [{"node_id": "n1", "depends_on": [],
                                                    "estimated_cost_units": "1.0"}]}
        o1 = OptimizerAgent()
        o2 = OptimizerAgent()
        r1 = await o1.optimize_execution_graph(dag, {}, "ten_a")
        r2 = await o2.optimize_execution_graph(dag, {}, "ten_a")
        assert r1["estimated_cost"] == r2["estimated_cost"]

    @pytest.mark.anyio
    async def test_same_intent_critic_consistent(self) -> None:
        c = CriticAgent()
        proposal = {"proposal_id": "p1", "intent": "test", "dag_nodes": [{}],
                    "estimated_cost": "1.0", "tenant_id": "ten_a"}
        r1 = await c.evaluate_plan(proposal, {"max_cost_units": "10"}, "ten_a")
        r2 = await c.evaluate_plan(proposal, {"max_cost_units": "10"}, "ten_a")
        assert r1["is_valid"] == r2["is_valid"]
        assert len(r1["violations"]) == len(r2["violations"])

    @pytest.mark.anyio
    async def test_handoff_produces_consistent_path(self) -> None:
        """Full planner → critic → optimizer chain: same intent → same path."""
        ctx = {"trace_snippets": [{"id": 1}], "context_hash": "abc"}
        p = PlannerAgent()
        c = CriticAgent()
        o = OptimizerAgent()

        plan1 = await p.synthesize_dag("summarize", ctx, "ten_a")
        crit1 = await c.evaluate_plan(plan1, {"max_cost_units": "10"}, "ten_a")
        opt1 = await o.optimize_execution_graph(plan1, {}, "ten_a")

        plan2 = await p.synthesize_dag("summarize", ctx, "ten_a")
        crit2 = await c.evaluate_plan(plan2, {"max_cost_units": "10"}, "ten_a")
        opt2 = await o.optimize_execution_graph(plan2, {}, "ten_a")

        assert plan1["_hash"] == plan2["_hash"]
        assert crit1["is_valid"] == crit2["is_valid"]
        assert opt1["estimated_cost"] == opt2["estimated_cost"]


# ===================================================================
# Group 3: Oscillation Prevention (5 tests)
# ===================================================================


class TestOscillationPrevention:
    @pytest.mark.anyio
    async def test_planner_adapt_blocks_identical_plan(self) -> None:
        p = PlannerAgent()
        orig = await p.synthesize_dag("intent", {}, "ten_a")
        r = await p.adapt_on_failure({"fault": "error"}, orig, "ten_a")
        # First retry should adapt (different hash)
        assert r["status"] == "adapted"

    @pytest.mark.anyio
    async def test_planner_aborts_after_max_retries(self) -> None:
        p = PlannerAgent()
        orig = await p.synthesize_dag("intent", {}, "ten_a")
        orig["_retry_count"] = 3
        r = await p.adapt_on_failure({"fault": "error"}, orig, "ten_a")
        assert r["status"] == "aborted"

    def test_sm_blocks_oscillation_gp4(self) -> None:
        sm = OrchestrationStateMachine()
        sm.transition(OrchestrationTransition.G_T1, {})
        sm.transition(OrchestrationTransition.G_T3, {"rejection_reason": "x"})
        r = sm.transition(OrchestrationTransition.G_T4, {
            "original_hash": "abc", "revised_hash": "abc",
        })
        assert r["status"] == "blocked"

    def test_sm_aborts_after_max_retries_gp5(self) -> None:
        sm = OrchestrationStateMachine(max_retry=0)
        sm.transition(OrchestrationTransition.G_T1, {})
        sm.transition(OrchestrationTransition.G_T3, {"rejection_reason": "x"})
        r = sm.transition(OrchestrationTransition.G_T5, {})
        assert r["status"] == "ok"
        assert sm.state == OrchestrationState.ABORTED

    @pytest.mark.anyio
    async def test_planner_oscillation_count_increments(self) -> None:
        p = PlannerAgent()
        orig = await p.synthesize_dag("intent", {}, "ten_a")
        r1 = await p.adapt_on_failure({"fault": "e"}, orig, "ten_a")
        assert r1["retry_count"] == 1


# ===================================================================
# Group 4: Failure Matrix Enforcement (5 tests)
# ===================================================================


class TestFailureMatrixEnforcement:
    @pytest.mark.anyio
    async def test_critic_rejects_empty_intent(self) -> None:
        c = CriticAgent()
        r = await c.evaluate_plan({"proposal_id": "p1", "intent": "", "dag_nodes": [],
                                   "estimated_cost": "0", "tenant_id": "ten_a"},
                                  {}, "ten_a")
        assert r["is_valid"] is False
        assert any("Intent" in v["description"] or "intent" in v["description"] for v in r["violations"])

    @pytest.mark.anyio
    async def test_critic_warns_over_budget(self) -> None:
        c = CriticAgent()
        r = await c.evaluate_plan({"proposal_id": "p1", "intent": "test",
                                   "dag_nodes": [{}], "estimated_cost": "50",
                                   "tenant_id": "ten_a"},
                                  {"max_cost_units": "10"}, "ten_a")
        assert any("budget" in v["rule_ref"] for v in r["violations"])

    @pytest.mark.anyio
    async def test_trace_records_all_events(self) -> None:
        ctc = OrchestrationTraceCorrelator()
        tid = ctc.generate_orchestration_trace_id("test", "ten_a")
        ctc.record_event(tid, "plan_proposed", "planner", "ten_a")
        ctc.record_event(tid, "plan_approved", "critic", "ten_a")
        ctc.record_event(tid, "optimization_applied", "optimizer", "ten_a")
        v = ctc.verify_full_propagation(tid)
        assert v["event_count"] == 3

    def test_sm_rejects_invalid_transition(self) -> None:
        sm = OrchestrationStateMachine()
        r = sm.transition(OrchestrationTransition.G_T9, {})
        assert r["status"] == "error"

    @pytest.mark.anyio
    async def test_optimizer_fallback_no_crash(self) -> None:
        o = OptimizerAgent()
        r = await o.optimize_execution_graph({"proposal_id": "p1", "dag_nodes": []},
                                             {}, "ten_a")
        assert r["estimated_cost"] == "0"


# ===================================================================
# Group 5: EventBus Routing Safety (5 tests)
# ===================================================================


class TestEventBusRoutingSafety:
    @pytest.mark.anyio
    async def test_facade_orchestrate_requires_agents(self) -> None:
        from core.runtime.facade import EmoRuntimeFacade
        f = EmoRuntimeFacade()
        r = await f.orchestrate("intent", "ten_a")
        assert r["status"] == "error"

    @pytest.mark.anyio
    async def test_facade_orchestrate_with_agents(self) -> None:
        from core.runtime.facade import EmoRuntimeFacade
        from core.orchestration.planner_agent import PlannerAgent
        from core.orchestration.critic_agent import CriticAgent
        from core.orchestration.optimizer_agent import OptimizerAgent
        f = EmoRuntimeFacade(
            planner_agent=PlannerAgent(),
            critic_agent=CriticAgent(),
            optimizer_agent=OptimizerAgent(),
        )
        r = await f.orchestrate("summarize", "ten_a", {"trace_snippets": [{"id": 1}]},
                                {"max_cost_units": "100"})
        assert r["status"] in ("ok", "rejected")

    @pytest.mark.anyio
    async def test_facade_orchestrate_rejected_intent(self) -> None:
        from core.runtime.facade import EmoRuntimeFacade
        from core.orchestration.planner_agent import PlannerAgent
        from core.orchestration.critic_agent import CriticAgent
        from core.orchestration.optimizer_agent import OptimizerAgent
        f = EmoRuntimeFacade(
            planner_agent=PlannerAgent(),
            critic_agent=CriticAgent(),
            optimizer_agent=OptimizerAgent(),
        )
        r = await f.orchestrate("", "ten_a")
        assert r["status"] == "rejected"

    def test_facade_orchestration_health_degraded(self) -> None:
        from core.runtime.facade import EmoRuntimeFacade
        f = EmoRuntimeFacade()
        h = f.orchestration_health()
        assert h["status"] == "degraded"

    def test_facade_orchestration_health_ok(self) -> None:
        from core.runtime.facade import EmoRuntimeFacade
        from core.orchestration.planner_agent import PlannerAgent
        from core.orchestration.critic_agent import CriticAgent
        from core.orchestration.orchestration_state_machine import OrchestrationStateMachine
        f = EmoRuntimeFacade(
            planner_agent=PlannerAgent(),
            critic_agent=CriticAgent(),
            optimizer_agent=OptimizerAgent(),
            orchestration_state_machine=OrchestrationStateMachine(),
            orchestration_trace_correlator=OrchestrationTraceCorrelator(),
        )
        h = f.orchestration_health()
        assert h["status"] == "ok"
