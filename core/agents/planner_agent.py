"""G.1 — Planner Agent: translates Intent into DAG Plans.

Cognitive orchestration layer — decides WHAT to do, never HOW.
Delegates execution to Runtime API. No direct agent communication.
No execute, run, allocate, or schedule methods.

Ref: DEVELOPER.md §16.1
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from core.interfaces.event_bus import IEventBus
from core.models.agent import AgentIdentity
from core.models.event import EventMetadata, EventTopic, ExecutionEvent
from core.models.planner import (
    Intent,
    IntentType,
    Plan,
    PlanStatus,
    PlanStep,
    PlanningContext,
    StepStatus,
)

logger = logging.getLogger("emo_ai.agents.planner")


class PlannerAgent:
    """Cognitive planner that translates Intent into executable DAG Plans.

    LAW 13: Dependencies injected via constructor.
    No direct execution — produces Plans for Runtime API consumption.
    No direct agent communication — interacts only via Runtime API and EventBus.
    """

    def __init__(
        self,
        identity: AgentIdentity,
        runtime_api: Any,
        event_bus: IEventBus,
    ) -> None:
        self._identity = identity
        self._runtime_api = runtime_api
        self._event_bus = event_bus

    def create_plan(
        self,
        intent: Intent,
        context: PlanningContext,
    ) -> Plan:
        """Analyze Intent and generate a validated DAG Plan.

        Publishes planning.started, then planning.completed or planning.failed.
        """
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        self._publish_event(
            EventTopic.PLANNING_STARTED,
            {"plan_id": plan_id, "intent_id": intent.intent_id, "intent_type": intent.type.value},
        )

        try:
            steps = self._generate_steps(intent, context)
            self._validate_dag(steps)
            self._validate_tools(steps, context)

            plan = Plan(
                plan_id=plan_id,
                intent_id=intent.intent_id,
                steps=steps,
                status=PlanStatus.VALIDATED,
            )

            self._publish_event(
                EventTopic.PLANNING_COMPLETED,
                {"plan_id": plan_id, "intent_id": intent.intent_id, "step_count": len(steps)},
            )
            return plan

        except (ValueError, KeyError) as exc:
            plan = Plan(
                plan_id=plan_id,
                intent_id=intent.intent_id,
                steps=[],
                status=PlanStatus.FAILED,
            )
            self._publish_event(
                EventTopic.PLANNING_FAILED,
                {"plan_id": plan_id, "intent_id": intent.intent_id, "error": str(exc)},
            )
            logger.warning("Planning failed for %s: %s", intent.intent_id, exc)
            return plan

    def submit_plan(self, plan: Plan) -> str:
        """Delegate plan submission to Runtime API. Does NOT execute."""
        if plan.status != PlanStatus.VALIDATED:
            raise ValueError(f"Cannot submit plan in status {plan.status.value}")

        submission_id = self._runtime_api.submit(plan)

        plan_with_status = Plan(
            plan_id=plan.plan_id,
            intent_id=plan.intent_id,
            steps=plan.steps,
            status=PlanStatus.SUBMITTED,
        )
        return submission_id

    def _generate_steps(
        self,
        intent: Intent,
        context: PlanningContext,
    ) -> List[PlanStep]:
        """Generate PlanSteps based on Intent type and available tools."""
        steps: List[PlanStep] = []

        if intent.type == IntentType.CODE_GENERATION:
            steps = [
                PlanStep(step_id="step-1", action="analyze_requirements", tool_name="analyzer", dependencies=[]),
                PlanStep(step_id="step-2", action="generate_code", tool_name="code_generator", dependencies=["step-1"]),
                PlanStep(step_id="step-3", action="validate_output", tool_name="validator", dependencies=["step-2"]),
            ]
        elif intent.type == IntentType.DATA_ANALYSIS:
            steps = [
                PlanStep(step_id="step-1", action="load_data", tool_name="data_loader", dependencies=[]),
                PlanStep(step_id="step-2", action="transform_data", tool_name="transformer", dependencies=["step-1"]),
                PlanStep(step_id="step-3", action="run_analysis", tool_name="analyzer", dependencies=["step-2"]),
                PlanStep(step_id="step-4", action="generate_report", tool_name="report_generator", dependencies=["step-3"]),
            ]
        elif intent.type == IntentType.SYSTEM_REFACTOR:
            steps = [
                PlanStep(step_id="step-1", action="scan_dependencies", tool_name="dependency_scanner", dependencies=[]),
                PlanStep(step_id="step-2", action="refactor_modules", tool_name="refactorer", dependencies=["step-1"]),
                PlanStep(step_id="step-3", action="run_tests", tool_name="test_runner", dependencies=["step-2"]),
            ]
        else:
            steps = [
                PlanStep(step_id="step-1", action="unknown_operation", tool_name="fallback_handler", dependencies=[]),
            ]

        return steps

    def _validate_dag(self, steps: List[PlanStep]) -> None:
        """Validate that the step graph is a DAG (no cycles, all deps exist).

        Raises ValueError if validation fails.
        """
        step_ids = {s.step_id for s in steps}
        for step in steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    raise ValueError(
                        f"Step '{step.step_id}' depends on missing step '{dep}'"
                    )

        visited: set[str] = set()
        in_stack: set[str] = set()

        def _has_cycle(node: str, graph: Dict[str, List[str]]) -> bool:
            visited.add(node)
            in_stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if _has_cycle(neighbor, graph):
                        return True
                elif neighbor in in_stack:
                    return True
            in_stack.discard(node)
            return False

        graph: Dict[str, List[str]] = {s.step_id: list(s.dependencies) for s in steps}
        for step_id in step_ids:
            if step_id not in visited:
                if _has_cycle(step_id, graph):
                    raise ValueError(f"Cycle detected involving step '{step_id}'")

    def _validate_tools(self, steps: List[PlanStep], context: PlanningContext) -> None:
        """Validate that all referenced tools exist in PlanningContext.

        Raises ValueError if a tool is not available.
        """
        available = set(context.available_tools)
        for step in steps:
            if step.tool_name not in available:
                raise ValueError(
                    f"Step '{step.step_id}' requires tool '{step.tool_name}' "
                    f"which is not available. Available: {sorted(available)}"
                )

    def _publish_event(self, topic: EventTopic, payload: Dict[str, Any]) -> None:
        """Publish a planning event to the EventBus."""
        event = ExecutionEvent(
            topic=topic,
            payload=payload,
            trace_id=str(uuid.uuid4()),
            metadata=EventMetadata(source=self._identity.id),
        )
        self._event_bus.publish(topic, event)
