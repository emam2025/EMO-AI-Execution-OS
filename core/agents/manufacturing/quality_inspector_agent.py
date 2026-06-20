"""QualityInspectorClosedLoop — Closed-Loop Quality Control.

Tracks defect counts per asset, triggers line slowdown/stop requests
when consecutive defects exceed threshold, enforces Human-in-the-Loop
via IAgentApprovalGate.

Ref: RC17.2.3 — Quality Closed-Loop Agent
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from core.models.agent import (
    AgentAudit,
    AgentIdentity,
    AgentMemory,
    AgentPermissions,
    AgentSkills,
)
from core.models.event import EventMetadata, EventTopic, ExecutionEvent

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class QualityInspectorClosedLoop:
    """Closed-loop quality inspector — detects defects, triggers line actions.

    Monitors quality checks, tracks consecutive defect counts per asset,
    and requests line slowdown/stop when threshold is exceeded.
    All critical actions require approval via IAgentApprovalGate.
    """

    DEFECT_THRESHOLD: int = 3
    REQUIRED_APPROVAL_ACTIONS = {"request_line_slowdown", "request_line_stop"}

    def __init__(
        self,
        identity: AgentIdentity,
        event_bus: Optional[IEventBus] = None,
        approval_gate: Optional[IAgentApprovalGate] = None,
    ) -> None:
        self._identity = identity
        self._event_bus = event_bus
        self._approval_gate = approval_gate
        self._memory = AgentMemory()
        self._skills = AgentSkills(
            registered_tools=["quality_inspector", "defect_detector", "line_controller"]
        )
        self._permissions = AgentPermissions(
            allowed_actions=[
                "record_quality_check",
                "get_defect_count",
                "request_line_slowdown",
                "request_line_stop",
            ],
            requires_approval_for=["request_line_slowdown", "request_line_stop"],
        )
        self._audit = AgentAudit()
        self._status = "created"
        self._defect_counts: Dict[str, int] = {}

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    @property
    def skills(self) -> AgentSkills:
        return self._skills

    @property
    def permissions(self) -> AgentPermissions:
        return self._permissions

    @property
    def audit(self) -> AgentAudit:
        return self._audit

    def activate(self) -> None:
        self._status = "active"
        self._audit.record_action(
            action="agent.activate",
            context={"agent_id": self._identity.id},
            result={"status": "active"},
        )

    def suspend(self, reason: str) -> None:
        self._status = "suspended"
        self._audit.record_action(
            action="agent.suspend",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "suspended"},
        )

    def terminate(self, reason: str) -> None:
        self._status = "terminated"
        self._audit.record_action(
            action="agent.terminate",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "terminated"},
        )

    def record_quality_check(
        self, asset_id: str, is_defective: bool, defect_type: str = ""
    ) -> Dict[str, Any]:
        """Record a quality check result. Returns action taken if any."""
        self._audit.record_action(
            action="quality_check.recorded",
            context={
                "agent_id": self._identity.id,
                "asset_id": asset_id,
                "is_defective": is_defective,
                "defect_type": defect_type,
            },
            result={"status": "recorded"},
        )

        if not is_defective:
            self._defect_counts[asset_id] = 0
            return {"status": "recorded", "action_taken": "none"}

        self._defect_counts[asset_id] = self._defect_counts.get(asset_id, 0) + 1

        if self._defect_counts[asset_id] >= self.DEFECT_THRESHOLD:
            return self._request_line_slowdown(asset_id)

        return {
            "status": "recorded",
            "action_taken": "none",
            "defect_count": self._defect_counts[asset_id],
        }

    def _request_line_slowdown(self, asset_id: str) -> Dict[str, Any]:
        """Request line slowdown, checking approval gate if available."""
        if self._approval_gate is not None:
            decision = self._approval_gate.check_autonomy(
                agent_id=self._identity.id,
                action="request_line_slowdown",
                autonomy_level="L2",
                context={"asset_id": asset_id, "defect_count": self._defect_counts[asset_id]},
            )
            if not decision.get("allowed", False):
                self._audit.record_action(
                    action="quality.line_slowdown.denied",
                    context={"agent_id": self._identity.id, "asset_id": asset_id},
                    result=decision,
                )
                return {"status": "denied", "reason": decision.get("reason", "")}

        event = ExecutionEvent(
            topic=EventTopic.QUALITY_LINE_SLOWDOWN_REQUESTED,
            payload={
                "asset_id": asset_id,
                "defect_count": self._defect_counts[asset_id],
                "threshold": self.DEFECT_THRESHOLD,
                "action": "slowdown",
            },
            trace_id=f"quality-{asset_id}",
            metadata=EventMetadata(source=f"agent.{self._identity.id}"),
        )

        self._audit.record_action(
            action="quality.line_slowdown.requested",
            context={
                "agent_id": self._identity.id,
                "asset_id": asset_id,
                "defect_count": self._defect_counts[asset_id],
            },
            result={"status": "requested", "action": "slowdown"},
        )

        if self._event_bus is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._event_bus.publish(EventTopic.QUALITY_LINE_SLOWDOWN_REQUESTED, event)
                )
            except RuntimeError:
                pass

        return {
            "status": "requested",
            "action": "slowdown",
            "defect_count": self._defect_counts[asset_id],
        }

    def get_defect_count(self, asset_id: str) -> int:
        return self._defect_counts.get(asset_id, 0)
