"""Phase F2 — Control Plane & Autoscaler: Data Models & Enums.

Mirrors artifacts/design/f2/models/02_scaling_and_health_models.py
for runtime importability. All types are used by core/runtime/control_plane/.

Ref: Canon LAW 5, LAW 8, LAW 11
Ref: DEVELOPER.md §15.9
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ScalingSignal(str, Enum):
    UP = "up"
    DOWN = "down"
    HOLD = "hold"
    DRAIN = "drain"


class WorkerState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DRAINING = "draining"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


class WorkerDrainingState(str, Enum):
    """Phases of the worker draining lifecycle (§15.9.3)."""
    MARK_DRAINING = "mark_draining"
    STOP_NEW_LEASES = "stop_new_leases"
    AWAIT_COMPLETION = "await_completion"
    RELEASE_LEASES = "release_leases"
    TERMINATE = "terminate"


class DegradationLevel(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class HealthEventType(str, Enum):
    HEALTHY = "worker.health.healthy"
    DEGRADED = "worker.health.degraded"
    CRITICAL = "worker.health.critical"
    RECOVERED = "worker.health.recovered"
    PROBE_FAILED = "worker.health.probe_failed"


@dataclass
class LoadMetric:  # LAW-5
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    queue_depth: int = 0
    avg_latency_ms: float = 0.0
    active_leases: int = 0


@dataclass
class ScalingPolicy:  # LAW-11
    min_workers: int = 1
    max_workers: int = 32
    target_utilization: float = 0.70
    cooldown_sec: float = 60.0
    hysteresis_pct: float = 0.10
    scale_step: int = 2


@dataclass
class ScalingSignalRecord:  # LAW-5
    timestamp: float = 0.0
    signal: ScalingSignal = ScalingSignal.HOLD
    previous_count: int = 0
    target_count: int = 0
    reason: str = ""


@dataclass
class ScalingReceipt:  # LAW-8
    previous_count: int = 0
    target_count: int = 0
    actual_count: int = 0
    signal: ScalingSignal = ScalingSignal.HOLD
    cooldown_until: float = 0.0
    reason: str = ""


@dataclass
class HealthProbeResult:  # LAW-5
    worker_id: str = ""
    alive: bool = False
    state: WorkerState = WorkerState.UNKNOWN
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    last_seen: float = 0.0
    latency_ms: float = 0.0


@dataclass
class HealthEvent:  # LAW-5
    worker_id: str = ""
    previous_state: WorkerState = WorkerState.UNKNOWN
    current_state: WorkerState = WorkerState.UNKNOWN
    degradation: DegradationLevel = DegradationLevel.NONE
    reason: str = ""
    timestamp: float = 0.0
    event_type: HealthEventType = HealthEventType.HEALTHY


@dataclass
class EvictionReceipt:  # LAW-8
    worker_id: str = ""
    evicted: bool = False
    state: WorkerState = WorkerState.TERMINATED
    reason: str = ""
    leases_lost: int = 0


@dataclass
class DrainReceipt:  # LAW-8
    worker_id: str = ""
    success: bool = False
    state: WorkerState = WorkerState.HEALTHY
    leases_released: int = 0
    reason: str = ""


@dataclass
class ClusterSnapshot:  # LAW-5
    worker_count: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    draining_count: int = 0
    load: Optional[LoadMetric] = None
    timestamp: float = 0.0


@dataclass
class Correction:  # RULE-1
    action: str = ""
    worker_id: str = ""
    reason: str = ""
    priority: int = 5


@dataclass
class DeltaReport:  # RULE-1
    drift_detected: bool = False
    worker_deficit: int = 0
    worker_surplus: int = 0
    corrections: List[Correction] = field(default_factory=list)
    observed_timestamp: float = 0.0


@dataclass
class ReconcileReport:  # LAW-11
    observed_workers: int = 0
    desired_workers: int = 0
    corrections_applied: int = 0
    corrections_pending: int = 0
    drift_count: int = 0
    timestamp: float = 0.0


@dataclass
class ScheduleReceipt:  # LAW-11
    corrections_scheduled: int = 0
    estimated_completion: float = 0.0
    batch_id: str = ""


@dataclass
class PolicyResult:  # LAW-8
    applied: bool = False
    signal: ScalingSignal = ScalingSignal.HOLD
    reason: str = ""
    cooldown_until: float = 0.0


@dataclass
class ControlPlaneState:  # LAW-5
    active_workers: int = 0
    draining_workers: List[str] = field(default_factory=list)
    current_replica: int = 0
    desired_replica: int = 0
    last_reconcile: float = 0.0
    scaling_signal: ScalingSignal = ScalingSignal.HOLD
    errors: List[str] = field(default_factory=list)
