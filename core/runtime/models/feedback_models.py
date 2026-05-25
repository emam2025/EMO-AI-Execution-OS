"""Phase D9 — Feedback Loop Data Models.

6 data models and supporting enums for the Runtime Intelligence
Feedback Loop.

LAW 5: All execution events are observable.
LAW 11: No global state — feedback state is per-instance.
LAW 12: All events carry trace_id.
LAW 14-16: CodeGraph-Driven Decomposition Laws.

Ref: DEVELOPER.md §5.3 (Self-Tuning), §5.4 (Guardrails)
Ref: Canon LAW 5, LAW 7, LAW 11, LAW 14-16
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class WeightTarget(str, Enum):
    W_GRAPH = "w_graph"
    W_SEM = "w_sem"
    COUPLING_THRESHOLD = "coupling_threshold"
    RISK_THRESHOLD = "risk_threshold"
    STRATEGY_WEIGHT = "strategy_weight"


class FeedbackState(str, Enum):
    IDLE = "idle"
    TRACE_CAPTURED = "trace_captured"
    METRIC_AGGREGATED = "metric_aggregated"
    THRESHOLD_CHECKED = "threshold_checked"
    WEIGHT_ADJUSTED = "weight_adjusted"
    COMMITTED = "committed"
    ALERT_TRIGGERED = "alert_triggered"
    ENFORCEMENT_GATE = "enforcement_gate"
    REJECTED = "rejected"
    NO_OP = "no_op"
    COOLDOWN = "cooldown"
    ERROR = "error"


class DriftSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    BLOCKING = "blocking"


class ViolationType(str, Enum):
    COUPLING_INCREASE = "coupling_increase"
    RISK_SCORE_EXCEEDED = "risk_score_exceeded"
    BOUNDARY_VIOLATION = "boundary_violation"
    INFRASTRUCTURE_LEAKAGE = "infrastructure_leakage"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    HOTSPOT_DETECTED = "hotspot_detected"
    DECOMPOSITION_REQUIRED = "decomposition_required"


class UpdateOutcome(str, Enum):
    ADJUSTED = "adjusted"
    NO_OP = "no_op"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    ALERTED = "alerted"


class FeedbackSignal(str, Enum):
    EXECUTION_SUCCESS = "execution_success"
    EXECUTION_FAILURE = "execution_failure"
    RETRY_ATTEMPTED = "retry_attempted"
    TIMEOUT_OCCURRED = "timeout_occurred"
    QUOTA_EXCEEDED = "quota_exceeded"
    LEASE_EXPIRED = "lease_expired"
    COUPLING_DRIFT = "coupling_drift"
    REPLAY_MISMATCH = "replay_mismatch"


@dataclass
class TraceEvent:
    """Single execution trace record captured from EventBus."""
    trace_id: str = ""
    execution_id: str = ""
    node_id: str = ""
    tool_name: str = ""
    outcome: ExecutionOutcome = ExecutionOutcome.SUCCESS
    duration_ms: float = 0.0
    resource_consumed: Dict[str, float] = field(default_factory=dict)
    feedback_signals: List[str] = field(default_factory=list)
    timestamp: float = 0.0


@dataclass
class WeightUpdateSignal:
    """Signal to apply a dynamic weight adjustment.

    Guards:
      - confidence >= 0.75
      - sample_size >= 20
      - target weight stays within [0.2, 0.8]
    """
    signal_id: str = ""
    source_metric: str = ""
    target_component: WeightTarget = WeightTarget.W_GRAPH
    delta: float = 0.0
    confidence: float = 0.0
    sample_size: int = 0
    success_rate: float = 0.0
    applied_at: float = 0.0
    reason: str = ""


@dataclass
class DriftAlert:
    """Alert raised when architecture drift is detected.

    Thresholds:
      - coupling delta > 0.05 → WARNING
      - coupling delta > 0.1  → BLOCK
      - risk score ↑ > 10     → BLOCK
    """
    alert_id: str = ""
    baseline_hash: str = ""
    current_hash: str = ""
    deviation_score: float = 0.0
    violation_type: str = ""
    severity: str = "warning"
    source_module: str = ""
    target_module: str = ""
    action_required: str = ""
    law_refs: List[str] = field(default_factory=list)
    timestamp: float = 0.0


@dataclass
class HotspotProfile:
    """Runtime hotspot profile for a node or tool.

    LAW 16: risk_score > 0.8 → decomposition required.
    """
    node_id: str = ""
    execution_count: int = 0
    failure_count: int = 0
    failure_rate: float = 0.0
    failure_patterns: List[Dict[str, Any]] = field(default_factory=list)
    avg_duration_ms: float = 0.0
    coupling_score: float = 0.0
    coupling_increase: float = 0.0
    risk_score: float = 0.0
    is_hotspot: bool = False
    recommendation: str = "none"


@dataclass
class FeedbackPolicy:
    """Policy rules governing the feedback loop weight updates.

    Ref: §5.3 — Self-Tuning boost thresholds
    Ref: §5.4 — SafeWeightBoundaries
    """
    min_confidence: float = 0.75
    min_sample_size: int = 20
    weight_min: float = 0.2
    weight_max: float = 0.8
    max_adjustments_per_hour: int = 3
    cooldown_minutes: int = 20
    drift_warning_threshold: float = 0.05
    drift_block_threshold: float = 0.1
    risk_warning_delta: float = 5.0
    risk_block_delta: float = 10.0
    hotspot_coupling_threshold: float = 0.7
    hotspot_failure_rate: float = 0.2
    hotspot_min_executions: int = 100
    window_size: int = 50
