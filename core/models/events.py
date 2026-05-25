from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

EVENT_SCHEMA_VERSION = "1.0.0"

EventType = Literal[
    "NODE_STARTED",
    "NODE_COMPLETED",
    "NODE_FAILED",
    "STATE_TRANSITION",
    "ARCHITECTURE_DRIFT",
    "BOUNDARY_VIOLATION",
    "DISPATCH_STARTED",
    "DISPATCH_COMPLETED",
    "DISPATCH_FAILED",
    "RETRY_DECISION",
    "LEASE_ACQUIRED",
    "LEASE_RELEASED",
    "LEASE_EXPIRED",
    "CHECKPOINT_CREATED",
    "EXECUTION_PLANNED",
    "EXECUTION_CANCELLED",
    "EXECUTION_COMPLETED",
]


@dataclass
class ExecutionEvent:
    event_id: str
    event_type: EventType
    timestamp: float
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    session_id: str = ""


@dataclass
class EventSubscription:
    topic: str
    handler: Any


TraceID = str


def make_trace_id() -> str:
    import uuid
    return uuid.uuid4().hex[:16]
