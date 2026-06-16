"""G.2 — Critic Agent: reviews Plans and detects gaps.

Analytical agent — reviews DAG structure, dependency completeness,
and resource feasibility. No execution logic, no Runtime interaction.

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
from core.models.planner import Plan, PlanStatus, PlanningContext
from core.models.critic import CriticDecision, CriticReport

logger = logging.getLogger("emo_ai.agents.critic")

MAX_STEPS_PER_PLAN = 50
MAX_DEPENDENCIES_PER_STEP = 10


class CriticAgent:
    """Analytical agent that reviews Plans for correctness and gaps.

    LAW 13: Dependencies injected via constructor.
    No execution — produces CriticReport only.
    """

    def __init__(
        self,
        identity: AgentIdentity,
        event_bus: IEventBus,
    ) -> None:
        self._identity = identity
        self._event_bus = event_bus

    def review_plan(
        self,
        plan: Plan,
        context: PlanningContext,
    ) -> CriticReport:
        """Review a Plan and produce a CriticReport with decision and reasons.

        Publishes CRITIC_STARTED, then CRITIC_APPROVED or CRITIC_REJECTED.
        """
        self._publish_event(
            EventTopic.CRITIC_STARTED,
            {"plan_id": plan.plan_id, "intent_id": plan.intent_id},
        )

        reasons: List[str] = []
        adaptations: List[str] = []

        if plan.status != PlanStatus.VALIDATED:
            reasons.append(f"Plan is in status '{plan.status.value}', expected 'validated'")

        if len(plan.steps) > MAX_STEPS_PER_PLAN:
            reasons.append(
                f"Plan has {len(plan.steps)} steps, exceeds limit of {MAX_STEPS_PER_PLAN}"
            )

        step_ids = {s.step_id for s in plan.steps}
        for step in plan.steps:
            if len(step.dependencies) > MAX_DEPENDENCIES_PER_STEP:
                reasons.append(
                    f"Step '{step.step_id}' has {len(step.dependencies)} deps, "
                    f"exceeds limit of {MAX_DEPENDENCIES_PER_STEP}"
                )
            for dep in step.dependencies:
                if dep not in step_ids:
                    reasons.append(
                        f"Step '{step.step_id}' depends on missing step '{dep}'"
                    )
                    adaptations.append(f"Add missing step '{dep}' or remove dependency")

        tool_set = set(context.available_tools)
        for step in plan.steps:
            if step.tool_name not in tool_set:
                reasons.append(
                    f"Step '{step.step_id}' requires unavailable tool '{step.tool_name}'"
                )
                adaptations.append(f"Replace tool '{step.tool_name}' with available alternative")

        seen_actions = [s.action for s in plan.steps]
        for i, action in enumerate(seen_actions):
            if seen_actions.count(action) > 1:
                idx = seen_actions.index(action)
                if i != idx:
                    reasons.append(f"Duplicate action '{action}' in steps")
                    adaptations.append(f"Merge duplicate steps for action '{action}'")

        if not reasons:
            decision = CriticDecision.APPROVED
        elif adaptations:
            decision = CriticDecision.NEEDS_ADAPTATION
        else:
            decision = CriticDecision.REJECTED

        report = CriticReport(
            plan_id=plan.plan_id,
            decision=decision,
            reasons=reasons,
            suggested_adaptations=adaptations,
        )

        topic = (
            EventTopic.CRITIC_APPROVED
            if decision == CriticDecision.APPROVED
            else EventTopic.CRITIC_REJECTED
        )
        self._publish_event(
            topic,
            {
                "plan_id": plan.plan_id,
                "decision": decision.value,
                "reason_count": len(reasons),
            },
        )

        return report

    def _publish_event(self, topic: EventTopic, payload: Dict[str, Any]) -> None:
        """Publish a critic event to the EventBus."""
        event = ExecutionEvent(
            topic=topic,
            payload=payload,
            trace_id=str(uuid.uuid4()),
            metadata=EventMetadata(source=self._identity.id),
        )
        self._event_bus.publish(topic, event)
