"""Safety Gate Implementation.

Enforces safety limits with Default Deny logic and mandatory event publishing.

Ref: P8.1 — Safety Limits & Policy Gate
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

from core.models.safety import SafetyDecision, SafetyLimitType, SafetyLimits


class SafetyGate:
    """Evaluates execution contexts against safety limits.

    Default Deny: any violation returns allowed=False with mandatory event publishing.
    No silent fallbacks. No try/except suppression.
    """

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus

    def _publish_violation(
        self,
        violation_type: SafetyLimitType,
        context: Dict[str, Any],
        limits: SafetyLimits,
        reason: str,
    ) -> None:
        """Publish safety violation event synchronously if event_bus is available."""
        if self._event_bus is not None:
            import asyncio
            from core.models.event import EventTopic, ExecutionEvent

            event = ExecutionEvent(
                topic=EventTopic.SAFETY_VIOLATION,
                trace_id=f"safety-{violation_type.value}",
                payload={
                    "violation_type": violation_type.value,
                    "reason": reason,
                    "context": context,
                    "limits": {
                        "max_tokens": limits.max_tokens,
                        "max_cost_usd": limits.max_cost_usd,
                        "max_runtime_seconds": limits.max_runtime_seconds,
                    },
                },
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._event_bus.publish(EventTopic.SAFETY_VIOLATION, event)
                )
            except RuntimeError:
                pass

    def evaluate(
        self, context: Dict[str, Any], limits: SafetyLimits
    ) -> SafetyDecision:
        """Evaluate context against safety limits. Default Deny on any violation."""

        # Check token limit
        tokens = context.get("tokens", 0)
        if tokens > limits.max_tokens:
            reason = f"Token limit exceeded: {tokens} > {limits.max_tokens}"
            self._publish_violation(
                SafetyLimitType.TOKEN_LIMIT, context, limits, reason
            )
            return SafetyDecision(
                allowed=False, reason=reason, violation_type=SafetyLimitType.TOKEN_LIMIT
            )

        # Check cost limit
        cost = context.get("estimated_cost", 0.0)
        if cost > limits.max_cost_usd:
            reason = f"Cost limit exceeded: ${cost} > ${limits.max_cost_usd}"
            self._publish_violation(
                SafetyLimitType.COST_LIMIT, context, limits, reason
            )
            return SafetyDecision(
                allowed=False, reason=reason, violation_type=SafetyLimitType.COST_LIMIT
            )

        # Check runtime limit
        runtime = context.get("estimated_runtime", 0.0)
        if runtime > limits.max_runtime_seconds:
            reason = f"Runtime limit exceeded: {runtime}s > {limits.max_runtime_seconds}s"
            self._publish_violation(
                SafetyLimitType.RUNTIME_LIMIT, context, limits, reason
            )
            return SafetyDecision(
                allowed=False,
                reason=reason,
                violation_type=SafetyLimitType.RUNTIME_LIMIT,
            )

        # All checks passed — allow execution
        return SafetyDecision(allowed=True, reason="Within all safety limits")
