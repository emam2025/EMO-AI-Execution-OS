"""AuditEventConsumption — validates every EventBus topic has active subscribers."""

# LAW-5: Observable — all event routing validated
# LAW-8: Traceable — every audit operation carries audit_trace_id
# LAW-11: No Global State — per-instance topic registry

from __future__ import annotations

import dataclasses
import hashlib
import time
from typing import Any, Dict, List, Optional, Protocol


@dataclasses.dataclass(frozen=True)
class TopicCheckResult:
    topic: str
    subscriber_count: int
    has_active_subscriber: bool
    is_dead_topic: bool
    detail: str


@dataclasses.dataclass(frozen=True)
class AuditEventReport:
    timestamp_ns: int
    audit_trace_id: str
    total_topics: int
    dead_topics: int
    topics: List[TopicCheckResult]
    passed: bool
    summary: str


REQUIRED_TOPICS = [
    "runtime.execution",
    "runtime.health",
    "runtime.scaling",
    "runtime.resource",
    "runtime.quota",
    "runtime.drift",
    "runtime.canary.metrics",
    "runtime.canary.alerts",
    "runtime.canary.sessions",
    "runtime.canary.replay",
    "runtime.readiness.canary",
    "runtime.audit.wiring",
    "runtime.stability",
]


class AuditEventConsumption:
    def __init__(self, event_bus: Any = None):
        raw = f"audit_events_{time.time_ns()}"
        self._trace_id = "ae_" + hashlib.sha256(raw.encode()).hexdigest()[:28]
        self._event_bus = event_bus

    @property
    def audit_trace_id(self) -> str:
        return self._trace_id

    def audit_topics(self, event_bus: Any) -> AuditEventReport:
        checks: List[TopicCheckResult] = []
        dead = 0

        for topic in REQUIRED_TOPICS:
            subscribers = []
            try:
                if hasattr(event_bus, "_subscriptions") and topic in event_bus._subscriptions:
                    subscribers = event_bus._subscriptions[topic]
                count = len(subscribers) if subscribers else 0
            except Exception:
                count = 0

            is_dead = count == 0
            if is_dead:
                dead += 1

            checks.append(TopicCheckResult(
                topic=topic,
                subscriber_count=count,
                has_active_subscriber=count > 0,
                is_dead_topic=is_dead,
                detail=(
                    f"{count} subscriber(s)" if count > 0
                    else "DEAD TOPIC — no subscribers"
                ),
            ))

        passed = dead == 0
        report = AuditEventReport(
            timestamp_ns=time.time_ns(),
            audit_trace_id=self._trace_id,
            total_topics=len(checks),
            dead_topics=dead,
            topics=checks,
            passed=passed,
            summary=(
                "ALL TOPICS HAVE SUBSCRIBERS — 0 dead topics"
                if passed
                else f"{dead} DEAD TOPICS DETECTED"
            ),
        )

        if self._event_bus is not None:
            try:
                from core.models.events import ExecutionEvent, EventType
                event = ExecutionEvent(
                    event_id=self._trace_id[:16],
                    event_type=EventType.STATE_TRANSITION,
                    timestamp_ns=report.timestamp_ns,
                    payload={
                        "action": "audit_event_consumption_complete",
                        "audit_trace_id": self._trace_id,
                        "passed": report.passed,
                        "total": report.total_topics,
                        "dead": report.dead_topics,
                    },
                )
                self._event_bus.publish("runtime.audit.wiring", event)
            except Exception:
                pass

        return report
