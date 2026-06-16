"""Event Domain Models for Execution Event Stream.

Pure data structures using stdlib only. Zero internal imports.

Ref: P6.1 — Event Domain Models & EventBus Protocol
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


class EventTopic(Enum):
    """Topics for event classification and subscription routing."""

    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    STATE_TRANSITION = "state_transition"
    ARCHITECTURE_DRIFT = "architecture_drift"
    AGENT_STATE_CHANGED = "agent_state_changed"
    ASSET_REGISTERED = "asset_registered"
    ASSET_REMOVED = "asset_removed"
    TWIN_STATE_UPDATED = "twin_state_updated"
    POLICY_EVALUATED = "policy_evaluated"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    SAFETY_VIOLATION = "safety_violation"
    GUARDRAIL_ALERT = "guardrail_alert"
    METRIC_RECORDED = "metric_recorded"
    SPAN_COMPLETED = "span_completed"
    CONNECTOR_READ_SUCCESS = "connector_read_success"
    CONNECTOR_READ_FAILURE = "connector_read_failure"
    OEE_CALCULATED = "oee_calculated"
    PREDICTIVE_ALERT = "predictive_alert"
    QUALITY_LINE_SLOWDOWN_REQUESTED = "quality_line_slowdown_requested"
    SECURITY_VIOLATION = "security_violation"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    PATIENT_VITALS_UPDATED = "patient_vitals_updated"
    ANOMALY_DETECTED = "anomaly_detected"
    COMPLIANCE_VIOLATION = "compliance_violation"
    TREND_ANALYSIS_REPORT = "trend_analysis_report"
    PLANNING_STARTED = "planning_started"
    PLANNING_COMPLETED = "planning_completed"
    PLANNING_FAILED = "planning_failed"
    CRITIC_STARTED = "critic_started"
    CRITIC_APPROVED = "critic_approved"
    CRITIC_REJECTED = "critic_rejected"
    PLAN_ADAPTED = "plan_adapted"


@dataclass(frozen=True)
class EventMetadata:
    """Metadata attached to every event for tracing and context."""

    source: str
    worker_id: Optional[str] = None
    custom_tags: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionEvent:
    """Core event model for the execution event stream.

    Every event carries a trace_id for distributed tracing across services.
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    topic: EventTopic = EventTopic.NODE_STARTED
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    metadata: Optional[EventMetadata] = None
