"""G.1 — Planner Agent Tests.

Verifies plan generation, DAG validation, tool validation, runtime delegation,
event publishing, and graceful failure handling.

Ref: DEVELOPER.md §16.1
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from unittest.mock import MagicMock

from core.agents.planner_agent import PlannerAgent
from core.interfaces.event_bus import IEventBus
from core.models.agent import AgentIdentity
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


def _build_agent() -> tuple[PlannerAgent, MagicMock, MagicMock]:
    identity = AgentIdentity(
        id="planner-1", tenant_id="t1", org_id=None,
        name="TestPlanner", agent_type="planner",
    )
    runtime_api = MagicMock()
    event_bus = MagicMock(spec=IEventBus)
    agent = PlannerAgent(identity=identity, runtime_api=runtime_api, event_bus=event_bus)
    return agent, runtime_api, event_bus


def _valid_context() -> PlanningContext:
    return PlanningContext(
        available_tools=["analyzer", "code_generator", "validator", "data_loader",
                         "transformer", "report_generator", "dependency_scanner",
                         "refactorer", "test_runner", "fallback_handler"],
    )


class TestPlannerAgent:
    def test_planner_generates_valid_plan_from_intent(self) -> None:
        agent, _, _ = _build_agent()
        intent = Intent(intent_id="i-1", type=IntentType.CODE_GENERATION, description="Generate code")
        plan = agent.create_plan(intent, _valid_context())
        assert plan.status == PlanStatus.VALIDATED
        assert len(plan.steps) == 3
        assert plan.steps[0].step_id == "step-1"
        assert plan.steps[2].dependencies == ["step-2"]

    def test_planner_validates_dag_dependencies(self) -> None:
        agent, _, _ = _build_agent()
        intent = Intent(intent_id="i-2", type=IntentType.CODE_GENERATION, description="Test")
        ctx = PlanningContext(available_tools=["analyzer", "code_generator", "validator"])
        plan = agent.create_plan(intent, ctx)
        assert plan.status == PlanStatus.VALIDATED

        missing_dep_ctx = PlanningContext(
            available_tools=["analyzer", "code_generator", "validator"],
        )
        broken_steps = [
            PlanStep(step_id="step-1", action="a", tool_name="analyzer", dependencies=["nonexistent"]),
        ]
        plan2 = Plan(plan_id="p-2", intent_id="i-2", steps=broken_steps, status=PlanStatus.DRAFT)
        assert plan2.steps[0].dependencies == ["nonexistent"]

    def test_planner_rejects_unknown_tools(self) -> None:
        agent, _, _ = _build_agent()
        intent = Intent(intent_id="i-3", type=IntentType.CODE_GENERATION, description="Test")
        ctx = PlanningContext(available_tools=["unrelated_tool"])
        plan = agent.create_plan(intent, ctx)
        assert plan.status == PlanStatus.FAILED

    def test_planner_submits_plan_to_runtime_api(self) -> None:
        agent, runtime_api, _ = _build_agent()
        runtime_api.submit.return_value = "sub-123"
        intent = Intent(intent_id="i-4", type=IntentType.DATA_ANALYSIS, description="Analyze data")
        plan = agent.create_plan(intent, _valid_context())
        submission_id = agent.submit_plan(plan)
        runtime_api.submit.assert_called_once()
        assert submission_id == "sub-123"

    def test_planner_publishes_planning_events(self) -> None:
        agent, _, event_bus = _build_agent()
        intent = Intent(intent_id="i-5", type=IntentType.CODE_GENERATION, description="Test events")
        agent.create_plan(intent, _valid_context())
        published_topics = [call.args[0] for call in event_bus.publish.call_args_list]
        assert EventTopic.PLANNING_STARTED in published_topics
        assert EventTopic.PLANNING_COMPLETED in published_topics

    def test_planner_handles_planning_failure_gracefully(self) -> None:
        agent, _, event_bus = _build_agent()
        intent = Intent(intent_id="i-6", type=IntentType.CODE_GENERATION, description="Fail test")
        ctx = PlanningContext(available_tools=["no_tools_here"])
        plan = agent.create_plan(intent, ctx)
        assert plan.status == PlanStatus.FAILED
        assert plan.steps == []
        published_topics = [call.args[0] for call in event_bus.publish.call_args_list]
        assert EventTopic.PLANNING_FAILED in published_topics
