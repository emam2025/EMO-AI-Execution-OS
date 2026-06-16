"""G.2 — Critic Agent & Adaptive Planner Tests.

Verifies plan review, rejection, adaptation, event publishing,
execution method absence, and end-to-end critique-adaptation loop.

Ref: DEVELOPER.md §16.2
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from unittest.mock import MagicMock

from core.agents.critic_agent import CriticAgent
from core.agents.adaptive_planner import AdaptivePlanner
from core.interfaces.event_bus import IEventBus
from core.models.agent import AgentIdentity
from core.models.critic import CriticDecision, CriticReport, ExecutionFeedback
from core.models.event import EventTopic
from core.models.planner import (
    Intent,
    IntentType,
    Plan,
    PlanStatus,
    PlanStep,
    PlanningContext,
    StepStatus,
)


def _build_agents() -> tuple[CriticAgent, AdaptivePlanner, MagicMock]:
    identity = AgentIdentity(
        id="critic-1", tenant_id="t1", org_id=None,
        name="TestCritic", agent_type="critic",
    )
    adapt_identity = AgentIdentity(
        id="adaptive-1", tenant_id="t1", org_id=None,
        name="TestAdaptive", agent_type="adaptive_planner",
    )
    event_bus = MagicMock(spec=IEventBus)
    critic = CriticAgent(identity=identity, event_bus=event_bus)
    adaptive = AdaptivePlanner(identity=adapt_identity, event_bus=event_bus)
    return critic, adaptive, event_bus


def _valid_context() -> PlanningContext:
    return PlanningContext(
        available_tools=["analyzer", "code_generator", "validator", "data_loader",
                         "transformer", "report_generator", "dependency_scanner",
                         "refactorer", "test_runner", "fallback_handler"],
    )


def _valid_plan() -> Plan:
    return Plan(
        plan_id="plan-test-1",
        intent_id="intent-1",
        steps=[
            PlanStep(step_id="step-1", action="analyze_requirements", tool_name="analyzer", dependencies=[]),
            PlanStep(step_id="step-2", action="generate_code", tool_name="code_generator", dependencies=["step-1"]),
            PlanStep(step_id="step-3", action="validate_output", tool_name="validator", dependencies=["step-2"]),
        ],
        status=PlanStatus.VALIDATED,
    )


class TestCriticAdaptive:
    def test_critic_approves_valid_plan(self) -> None:
        critic, _, _ = _build_agents()
        report = critic.review_plan(_valid_plan(), _valid_context())
        assert report.decision == CriticDecision.APPROVED
        assert report.reasons == []

    def test_critic_rejects_plan_with_missing_dependencies(self) -> None:
        critic, _, _ = _build_agents()
        bad_plan = Plan(
            plan_id="plan-bad-1",
            intent_id="intent-2",
            steps=[
                PlanStep(step_id="step-1", action="a", tool_name="analyzer", dependencies=["nonexistent"]),
            ],
            status=PlanStatus.VALIDATED,
        )
        report = critic.review_plan(bad_plan, _valid_context())
        assert report.decision != CriticDecision.APPROVED
        assert any("nonexistent" in r for r in report.reasons)

    def test_adaptive_planner_modifies_failed_plan(self) -> None:
        _, adaptive, _ = _build_agents()
        feedback = ExecutionFeedback(
            plan_id="plan-test-1",
            failed_step_id="step-2",
            error_type="TimeoutError",
            trace_summary="step-2 timed out",
        )
        adapted = adaptive.adapt_plan(_valid_plan(), feedback)
        assert adapted.status == PlanStatus.VALIDATED
        assert any("fallback" in s.step_id for s in adapted.steps)
        failed_step = next(s for s in adapted.steps if s.step_id == "step-2")
        assert failed_step.status == StepStatus.FAILED

    def test_critic_and_adaptive_publish_correct_events(self) -> None:
        critic, adaptive, event_bus = _build_agents()
        critic.review_plan(_valid_plan(), _valid_context())
        feedback = ExecutionFeedback(
            plan_id="plan-test-1", failed_step_id="step-2",
            error_type="TimeoutError", trace_summary="timeout",
        )
        adaptive.adapt_plan(_valid_plan(), feedback)
        published_topics = [call.args[0] for call in event_bus.publish.call_args_list]
        assert EventTopic.CRITIC_STARTED in published_topics
        assert EventTopic.CRITIC_APPROVED in published_topics
        assert EventTopic.PLAN_ADAPTED in published_topics

    def test_critic_has_no_execution_methods(self) -> None:
        import inspect
        critic_methods = [m for m in dir(CriticAgent) if not m.startswith("_")]
        adaptive_methods = [m for m in dir(AdaptivePlanner) if not m.startswith("_")]
        forbidden = {"execute", "run", "dispatch", "allocate", "schedule"}
        for method_name in critic_methods:
            assert method_name not in forbidden, f"CriticAgent has forbidden method: {method_name}"
        for method_name in adaptive_methods:
            assert method_name not in forbidden, f"AdaptivePlanner has forbidden method: {method_name}"

    def test_end_to_end_critique_and_adaptation_loop(self) -> None:
        critic, adaptive, event_bus = _build_agents()
        plan = _valid_plan()
        report = critic.review_plan(plan, _valid_context())
        assert report.decision == CriticDecision.APPROVED

        feedback = ExecutionFeedback(
            plan_id=plan.plan_id, failed_step_id="step-2",
            error_type="RuntimeError", trace_summary="step-2 failed at runtime",
        )
        adapted = adaptive.adapt_plan(plan, feedback)
        report2 = critic.review_plan(adapted, _valid_context())
        assert report2.decision == CriticDecision.APPROVED
        assert adapted.plan_id != plan.plan_id
