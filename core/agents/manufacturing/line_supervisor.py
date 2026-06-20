"""LineSupervisorAgent — Production Line Supervision.

Monitors production lines, triggers shutdowns, escalates anomalies.
Integrated with ITwinManager for twin queries and IEventBus for event publishing.

Ref: RC17.1.2 — Manufacturing Agents
Ref: RC17.1.3 — Manufacturing Agents Integration (TwinManager + Event Fabric)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.models.agent import (
    AgentAudit,
    AgentCost,
    AgentIdentity,
    AgentMemory,
    AgentPermissions,
    AgentRisk,
    AgentSkills,
)
from core.models.manufacturing import LineStatus, ProductionLine

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate
    from core.interfaces.event_bus import IEventBus
    from core.interfaces.industrial import ITwinManager


class LineSupervisorAgent:
    """Production line supervisor — monitors, shuts down, and escalates.

    Integrated with ITwinManager for production line state queries
    and IEventBus for lifecycle event publishing.
    """

    REQUIRED_APPROVAL_ACTIONS = {"line_shutdown", "emergency_stop"}

    def __init__(
        self,
        identity: AgentIdentity,
        twin_manager: Optional[ITwinManager] = None,
        event_bus: Optional[IEventBus] = None,
        approval_gate: Optional[IAgentApprovalGate] = None,
    ) -> None:
        self._identity = identity
        self._twin_manager = twin_manager
        self._event_bus = event_bus
        self._approval_gate = approval_gate
        self._memory = AgentMemory()
        self._skills = AgentSkills(
            registered_tools=["line_supervisor", "anomaly_detector"]
        )
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_line_status",
                "list_lines",
                "adjust_throughput",
                "line_shutdown",
                "emergency_stop",
                "report_anomaly",
            ],
            requires_approval_for=["line_shutdown", "emergency_stop"],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"
        self._lines: Dict[str, ProductionLine] = {}

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
    def risk(self) -> AgentRisk:
        return self._risk

    @property
    def cost(self) -> AgentCost:
        return self._cost

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

    def execute(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        ctx = context or {}
        requires_approval = task in self.REQUIRED_APPROVAL_ACTIONS

        if requires_approval and self._approval_gate is not None:
            decision = self._approval_gate.check_autonomy(
                agent_id=self._identity.id,
                action=task,
                autonomy_level="L2",
                context=ctx,
            )
            if not decision.get("allowed", False):
                self._audit.record_action(
                    action=f"agent.{task}.denied",
                    context={"agent_id": self._identity.id, "task": task},
                    result=decision,
                )
                return {"status": "denied", "reason": decision.get("reason", "")}

        self._audit.record_action(
            action=f"agent.{task}.executed",
            context={"agent_id": self._identity.id, "task": task},
            result={"status": "completed"},
        )
        return {"status": "completed", "task": task}

    def can_perform(self, action: str, context: Dict[str, Any]) -> Dict[str, Any]:
        allowed = self._permissions.can_perform(action)
        req_approval = self._permissions.requires_approval(action)
        return {
            "allowed": allowed,
            "requires_approval": req_approval,
            "reason": "Action permitted" if allowed else "Action denied",
            "policy_id": None,
        }

    def register_line(self, line: ProductionLine) -> None:
        self._lines[line.id] = line
        self._audit.record_action(
            action="line.registered",
            context={"line_id": line.id, "line_name": line.name},
            result={"status": "registered"},
        )

    def get_line_status(self, line_id: str) -> Optional[LineStatus]:
        """Query production line status from TwinManager or local cache."""
        if self._twin_manager is not None:
            twin_state = self._twin_manager.get_twin_state(line_id)
            status_str = twin_state.state.get("status", "")
            for member in LineStatus:
                if member.value == status_str:
                    return member
            return None
        line = self._lines.get(line_id)
        return line.status if line else None

    def shutdown_line(self, line_id: str) -> Dict[str, Any]:
        """Shutdown production line with approval gating, twin update, and event publish."""
        # 1. Check approval gate
        if self._approval_gate is not None:
            decision = self._approval_gate.check_autonomy(
                agent_id=self._identity.id,
                action="line_shutdown",
                autonomy_level="L2",
                context={"line_id": line_id},
            )
            if not decision.get("allowed", False):
                self._audit.record_action(
                    action="line.shutdown.denied",
                    context={"agent_id": self._identity.id, "line_id": line_id},
                    result=decision,
                )
                return {"status": "denied", "reason": decision.get("reason", "")}

        # 2. Update twin state if available
        if self._twin_manager is not None:
            self._twin_manager.update_twin_state(
                line_id, {"status": LineStatus.STOPPED.value}
            )

        # 3. Publish event if available
        if self._event_bus is not None:
            from core.models.event import EventTopic, ExecutionEvent

            event = ExecutionEvent(
                topic=EventTopic.TWIN_STATE_UPDATED,
                trace_id=f"line-supervisor-{self._identity.id}",
                payload={
                    "action": "line_shutdown",
                    "line_id": line_id,
                    "agent_id": self._identity.id,
                    "status": LineStatus.STOPPED.value,
                },
                metadata=None,
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._event_bus.publish(EventTopic.TWIN_STATE_UPDATED, event)
                )
            except RuntimeError:
                pass

        # 4. Record audit and complete
        self._audit.record_action(
            action="line.shutdown.completed",
            context={"agent_id": self._identity.id, "line_id": line_id},
            result={"status": "completed"},
        )
        return {"status": "completed", "line_id": line_id}
