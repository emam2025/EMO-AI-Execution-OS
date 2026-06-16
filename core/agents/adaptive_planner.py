"""G.2 — Adaptive Planner: modifies Plans based on ExecutionFeedback.

Adapts DAG structure by inserting fallback/retry steps after failures.
No execution logic, no Runtime interaction.

Ref: DEVELOPER.md §16.2
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from core.interfaces.event_bus import IEventBus
from core.models.agent import AgentIdentity
from core.models.event import EventMetadata, EventTopic, ExecutionEvent
from core.models.planner import Plan, PlanStep, PlanStatus, StepStatus
from core.models.critic import ExecutionFeedback

logger = logging.getLogger("emo_ai.agents.adaptive_planner")


class AdaptivePlanner:
    """Adapts Plans by inserting fallback/retry steps after failures.

    LAW 13: Dependencies injected via constructor.
    No execution — produces adapted Plan only.
    """

    def __init__(
        self,
        identity: AgentIdentity,
        event_bus: IEventBus,
    ) -> None:
        self._identity = identity
        self._event_bus = event_bus

    def adapt_plan(
        self,
        original_plan: Plan,
        feedback: ExecutionFeedback,
    ) -> Plan:
        """Adapt a Plan based on ExecutionFeedback.

        Inserts a fallback step after the failed step and re-links dependencies.
        Publishes PLAN_ADAPTED event. Returns new Plan with status VALIDATED.
        """
        existing_ids = {s.step_id for s in original_plan.steps}
        fallback_id = f"{feedback.failed_step_id}-fallback"
        counter = 1
        while fallback_id in existing_ids:
            fallback_id = f"{feedback.failed_step_id}-fallback-{counter}"
            counter += 1
        existing_ids.add(fallback_id)

        fallback_step = PlanStep(
            step_id=fallback_id,
            action=f"retry_{feedback.failed_step_id}",
            tool_name="fallback_handler",
            dependencies=[],
            status=StepStatus.PENDING,
        )

        adapted_steps: List[PlanStep] = []
        for step in original_plan.steps:
            if step.step_id == feedback.failed_step_id:
                adapted_steps.append(
                    PlanStep(
                        step_id=step.step_id,
                        action=step.action,
                        tool_name=step.tool_name,
                        dependencies=step.dependencies,
                        status=StepStatus.FAILED,
                    )
                )
                adapted_steps.append(fallback_step)
            else:
                new_deps = [
                    fallback_id if dep == feedback.failed_step_id else dep
                    for dep in step.dependencies
                ]
                adapted_steps.append(
                    PlanStep(
                        step_id=step.step_id,
                        action=step.action,
                        tool_name=step.tool_name,
                        dependencies=new_deps,
                        status=step.status,
                    )
                )

        adapted_plan = Plan(
            plan_id=f"{original_plan.plan_id}-adapted",
            intent_id=original_plan.intent_id,
            steps=adapted_steps,
            status=PlanStatus.VALIDATED,
        )

        self._publish_event(
            EventTopic.PLAN_ADAPTED,
            {
                "original_plan_id": original_plan.plan_id,
                "adapted_plan_id": adapted_plan.plan_id,
                "failed_step_id": feedback.failed_step_id,
                "fallback_step_id": fallback_id,
                "total_steps": len(adapted_steps),
            },
        )

        return adapted_plan

    def _publish_event(self, topic: EventTopic, payload: Dict[str, Any]) -> None:
        """Publish an adaptation event to the EventBus."""
        event = ExecutionEvent(
            topic=topic,
            payload=payload,
            trace_id=str(uuid.uuid4()),
            metadata=EventMetadata(source=self._identity.id),
        )
        self._event_bus.publish(topic, event)
