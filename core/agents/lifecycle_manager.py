"""Agent OS — Lifecycle Manager (Strict State Machine).

Manages agent state transitions: CREATED → ACTIVE → SUSPENDED → TERMINATED.

Ref: RC16.8.2 — Agent Lifecycle Manager
Ref: LAW 2 (Interface Authority)
Ref: LAW 9 (Governance Independence)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from core.models.agent import AgentAudit, AgentStatus

if TYPE_CHECKING:
    from core.interfaces.control_plane import IResourceManager
    from core.interfaces.event_bus import IEventBus
    from core.models.event import EventTopic, ExecutionEvent

from core.interfaces.agents import IAgentLifecycleManager


class AgentLifecycleManager(IAgentLifecycleManager):
    """Strict state machine for Agent lifecycle."""

    # ── Valid Transitions ─────────────────────────────────────
    VALID_TRANSITIONS: Dict[AgentStatus, set[AgentStatus]] = {
        AgentStatus.CREATED: {AgentStatus.ACTIVE, AgentStatus.TERMINATED},
        AgentStatus.ACTIVE: {AgentStatus.SUSPENDED, AgentStatus.TERMINATED},
        AgentStatus.SUSPENDED: {AgentStatus.ACTIVE, AgentStatus.TERMINATED},
        AgentStatus.TERMINATED: set(),  # Final — no transitions out
    }

    def __init__(
        self,
        resource_manager: IResourceManager,
        audit: Optional[AgentAudit] = None,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._rm = resource_manager
        self._audit = audit or AgentAudit()
        self._status_cache: Dict[str, AgentStatus] = {}
        self._event_bus = event_bus

    # ── Internal Helpers ──────────────────────────────────────

    def _validate_exists(self, agent_id: str) -> bool:
        """Check agent exists via IResourceManager."""
        return self._rm.get_resource(agent_id) is not None

    def _record(
        self,
        agent_id: str,
        action: str,
        old_status: AgentStatus,
        new_status: AgentStatus,
    ) -> None:
        """Record transition in cache + audit trail."""
        self._status_cache[agent_id] = new_status
        self._audit.record_action(
            action=f"lifecycle.{action}",
            context={"agent_id": agent_id, "old_status": old_status.value},
            result={"new_status": new_status.value},
        )
        # Publish event synchronously if event_bus is available
        if self._event_bus is not None:
            import asyncio
            from core.models.event import EventTopic, ExecutionEvent

            event = ExecutionEvent(
                topic=EventTopic.STATE_TRANSITION,
                trace_id=f"lifecycle-{agent_id}",
                payload={
                    "agent_id": agent_id,
                    "old_status": old_status.value,
                    "new_status": new_status.value,
                    "action": action,
                },
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._event_bus.publish(EventTopic.STATE_TRANSITION, event))
            except RuntimeError:
                pass

    # ── Protocol Implementation ───────────────────────────────

    def activate(self, agent_id: str) -> Dict[str, Any]:
        """Transition agent to ACTIVE state."""
        if not self._validate_exists(agent_id):
            return {"success": False, "error": "Agent not found"}

        current = self._status_cache.get(agent_id, AgentStatus.CREATED)

        if current == AgentStatus.TERMINATED:
            return {"success": False, "error": "Cannot activate terminated agent"}

        if current == AgentStatus.ACTIVE:
            return {"success": True, "status": current.value, "note": "Already active"}

        if AgentStatus.ACTIVE not in self.VALID_TRANSITIONS[current]:
            return {"success": False, "error": f"Invalid transition: {current.value} → active"}

        self._record(agent_id, "activate", current, AgentStatus.ACTIVE)
        return {"success": True, "status": AgentStatus.ACTIVE.value}

    def suspend(self, agent_id: str, reason: str) -> Dict[str, Any]:
        """Transition agent to SUSPENDED state."""
        if not self._validate_exists(agent_id):
            return {"success": False, "error": "Agent not found"}

        current = self._status_cache.get(agent_id, AgentStatus.CREATED)

        if current in (AgentStatus.TERMINATED, AgentStatus.SUSPENDED):
            return {"success": False, "error": f"Cannot suspend {current.value} agent"}

        self._record(agent_id, "suspend", current, AgentStatus.SUSPENDED)
        return {"success": True, "status": AgentStatus.SUSPENDED.value, "reason": reason}

    def terminate(self, agent_id: str, reason: str) -> Dict[str, Any]:
        """Transition agent to TERMINATED state (final)."""
        if not self._validate_exists(agent_id):
            return {"success": False, "error": "Agent not found"}

        current = self._status_cache.get(agent_id, AgentStatus.CREATED)

        if current == AgentStatus.TERMINATED:
            return {"success": False, "error": "Agent already terminated"}

        self._record(agent_id, "terminate", current, AgentStatus.TERMINATED)
        return {"success": True, "status": AgentStatus.TERMINATED.value, "reason": reason}

    def get_status(self, agent_id: str) -> Dict[str, Any]:
        """Get current agent status."""
        if not self._validate_exists(agent_id):
            return {"exists": False}

        status = self._status_cache.get(agent_id, AgentStatus.CREATED)
        return {"exists": True, "status": status.value, "agent_id": agent_id}
