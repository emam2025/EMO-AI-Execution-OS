"""Rollback Engine Implementation.

Event-driven rollback and containment with audit trail.

Ref: P8.3 — Rollback & Containment
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

from core.models.event import EventTopic, ExecutionEvent
from core.models.rollback import RollbackAction, RollbackScope, RollbackStatus


class RollbackEngine:
    """Event-driven rollback engine with scoped handlers and audit trail.

    Subscribes to GUARDRAIL_ALERT and SAFETY_VIOLATION events.
    Triggers rollback automatically on CRITICAL or HIGH severity.
    All actions are recorded in an in-memory audit log.
    """

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus
        self._handlers: Dict[RollbackScope, Callable[[str, str], Awaitable[bool]]] = {}
        self._audit_log: List[RollbackAction] = []
        self._subscription_ids: List[str] = []

    def register_handler(
        self,
        scope: RollbackScope,
        handler: Callable[[str, str], Awaitable[bool]],
    ) -> None:
        """Register a rollback handler for a specific scope."""
        self._handlers[scope] = handler

    def subscribe_to_events(self) -> None:
        """Subscribe to GUARDRAIL_ALERT and SAFETY_VIOLATION events."""
        if self._event_bus is None:
            return

        sub1 = self._event_bus.subscribe(
            EventTopic.GUARDRAIL_ALERT, self._handle_guardrail_alert
        )
        sub2 = self._event_bus.subscribe(
            EventTopic.SAFETY_VIOLATION, self._handle_safety_violation
        )
        self._subscription_ids.extend([sub1, sub2])

    def unsubscribe_from_events(self) -> None:
        """Unsubscribe from all events."""
        if self._event_bus is None:
            return

        for sub_id in self._subscription_ids:
            self._event_bus.unsubscribe(sub_id)
        self._subscription_ids.clear()

    async def _handle_guardrail_alert(self, event: ExecutionEvent) -> None:
        """Handle guardrail alert events. Trigger rollback on CRITICAL/HIGH."""
        severity = event.payload.get("severity", "")
        agent_id = event.payload.get("agent_id", "")

        if severity in ("critical", "high"):
            await self.trigger_rollback(
                scope=RollbackScope.AGENT,
                target_id=agent_id,
                reason=f"Guardrail alert: {event.payload.get('drift_type', 'unknown')}",
            )

    async def _handle_safety_violation(self, event: ExecutionEvent) -> None:
        """Handle safety violation events. Trigger rollback on any violation."""
        agent_id = event.payload.get("context", {}).get("agent_id", "unknown")
        violation_type = event.payload.get("violation_type", "unknown")

        await self.trigger_rollback(
            scope=RollbackScope.SESSION,
            target_id=agent_id,
            reason=f"Safety violation: {violation_type}",
        )

    async def trigger_rollback(
        self, scope: RollbackScope, target_id: str, reason: str
    ) -> RollbackAction:
        """Execute rollback for a given scope and target."""
        action = RollbackAction(
            scope=scope,
            target_id=target_id,
            reason=reason,
            status=RollbackStatus.PENDING,
        )

        handler = self._handlers.get(scope)
        if handler is None:
            # No handler registered — record as FAILED
            failed_action = RollbackAction(
                action_id=action.action_id,
                timestamp=action.timestamp,
                scope=scope,
                target_id=target_id,
                reason=reason,
                status=RollbackStatus.FAILED,
            )
            self._audit_log.append(failed_action)
            await self._publish_rollback_event(failed_action)
            return failed_action

        try:
            success = await handler(target_id, reason)
            if success:
                executed_action = RollbackAction(
                    action_id=action.action_id,
                    timestamp=action.timestamp,
                    scope=scope,
                    target_id=target_id,
                    reason=reason,
                    status=RollbackStatus.EXECUTED,
                )
                self._audit_log.append(executed_action)
                await self._publish_rollback_event(executed_action)
                return executed_action
            else:
                # Handler returned False — record as FAILED
                failed_action = RollbackAction(
                    action_id=action.action_id,
                    timestamp=action.timestamp,
                    scope=scope,
                    target_id=target_id,
                    reason=reason,
                    status=RollbackStatus.FAILED,
                )
                self._audit_log.append(failed_action)
                await self._publish_rollback_event(failed_action)
                return failed_action
        except Exception:
            # Handler raised exception — record as FAILED (no silent failure)
            failed_action = RollbackAction(
                action_id=action.action_id,
                timestamp=action.timestamp,
                scope=scope,
                target_id=target_id,
                reason=reason,
                status=RollbackStatus.FAILED,
            )
            self._audit_log.append(failed_action)
            await self._publish_rollback_event(failed_action)
            return failed_action

    async def _publish_rollback_event(self, action: RollbackAction) -> None:
        """Publish rollback event to event bus."""
        if self._event_bus is None:
            return

        import asyncio
        from core.models.event import ExecutionEvent as EE

        event = EE(
            topic=EventTopic.STATE_TRANSITION,
            trace_id=f"rollback-{action.action_id}",
            payload={
                "action_id": action.action_id,
                "scope": action.scope.value,
                "target_id": action.target_id,
                "reason": action.reason,
                "status": action.status.value,
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.STATE_TRANSITION, event)
            )
        except RuntimeError:
            pass

    def get_audit_log(self, target_id: str) -> List[RollbackAction]:
        """Get all rollback actions for a specific target."""
        return [action for action in self._audit_log if action.target_id == target_id]

    def get_all_actions(self) -> List[RollbackAction]:
        """Get all rollback actions in the audit log."""
        return list(self._audit_log)
