"""Phase F2 — Control Plane & Autoscaler: Load, Scaling & Health Models.

This file defines all data models and enums referenced by the four
F2 protocols in protocols/01_control_plane_protocols.py:

  - LoadMetric:       CPU, memory, queue depth, latency, active leases
  - ScalingSignal:    UP, DOWN, HOLD, DRAIN
  - ScalingPolicy:    Bounds, utilization target, cooldown, hysteresis
  - WorkerState:      HEALTHY, DEGRADED, DRAINING, TERMINATED, UNKNOWN
  - HealthProbeResult, DegradationLevel, HealthEvent, EvictionReceipt
  - ClusterSnapshot, ReconcileReport, DeltaReport, Correction, etc.

Ref: Canon LAW 5, LAW 8, LAW 11
Ref: DEVELOPER.md §15.9
Ref: ROADMAP Phase F2 — Autoscaler Models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════


class ScalingSignal(str, Enum):
    """Signals emitted by the Autoscaler after load evaluation.

    UP:    Increase worker count (utilization > target + hysteresis)
    DOWN:  Decrease worker count (utilization < target - hysteresis)
    HOLD:  Maintain current count (within hysteresis band)
    DRAIN: Scale down by draining workers gracefully
    """
    UP = "up"
    DOWN = "down"
    HOLD = "hold"
    DRAIN = "drain"


class WorkerState(str, Enum):
    """Lifecycle state of a worker node.

    HEALTHY:    Fully operational, accepting leases
    DEGRADED:   Operating with reduced capacity (high CPU/mem/latency)
    DRAINING:   Gracefully shutting down — no new leases, waiting for
                existing leases to complete
    TERMINATED: Stopped — resources released
    UNKNOWN:    State not yet determined or worker disappeared
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DRAINING = "draining"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


class WorkerDrainingState(str, Enum):
    """Phases of the worker draining lifecycle.

    Per §15.9.3 — Draining Lifecycle:
      MARK_DRAINING → STOP_NEW_LEASES → AWAIT_COMPLETION
      → RELEASE_LEASES → TERMINATE
    """
    MARK_DRAINING = "mark_draining"
    STOP_NEW_LEASES = "stop_new_leases"
    AWAIT_COMPLETION = "await_completion"
    RELEASE_LEASES = "release_leases"
    TERMINATE = "terminate"


class DegradationLevel(str, Enum):
    """Progressive degradation levels.

    NONE:     Within healthy thresholds
    MINOR:    Elevated resource usage but still operational
    MAJOR:    Significant resource pressure — may affect performance
    CRITICAL: Worker is failing — eviction required
    """
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class HealthEventType(str, Enum):
    """Types of health events published to EventBus."""
    HEALTHY = "worker.health.healthy"
    DEGRADED = "worker.health.degraded"
    CRITICAL = "worker.health.critical"
    RECOVERED = "worker.health.recovered"
    PROBE_FAILED = "worker.health.probe_failed"


class ReconciliationPhase(str, Enum):
    """Phases of the reconciliation loop interval strategy.

    §15.9.2 — Interval Strategy:
      OBSERVE  : every 5s  — collect cluster state
      EVALUATE : every 15s — compare vs desired, compute delta
      ACT      : every 30s — schedule and apply corrections
    """
    OBSERVE = "observe"
    EVALUATE = "evaluate"
    ACT = "act"


# ════════════════════════════════════════════════════════════════════
# Load & Scaling Models
# ════════════════════════════════════════════════════════════════════


@dataclass
class LoadMetric:
    """Snapshot of load metrics for a worker or cluster.

    Fields:
      cpu_pct:        CPU utilization percentage (0.0–100.0)
      mem_pct:        Memory utilization percentage (0.0–100.0)
      queue_depth:    Number of pending tasks in the worker queue
      avg_latency_ms: Average request latency in milliseconds
      active_leases:  Number of currently active leases
    """
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    queue_depth: int = 0
    avg_latency_ms: float = 0.0
    active_leases: int = 0


@dataclass
class ScalingPolicy:
    """Configuration for autoscaling behaviour.

    Fields:
      min_workers:        Minimum number of workers (floor)
      max_workers:        Maximum number of workers (ceiling)
      target_utilization: Desired utilization fraction (0.0–1.0).
                          Scaling acts to maintain this level.
      cooldown_sec:       Minimum seconds between scaling actions
                          to prevent oscillation (§15.9.4).
      hysteresis_pct:     Dead-band fraction around target_utilization.
                          Within this band, no scaling action is taken.
      scale_step:         Number of workers to add/remove per action.
    """
    min_workers: int = 1
    max_workers: int = 32
    target_utilization: float = 0.70
    cooldown_sec: float = 60.0
    hysteresis_pct: float = 0.10
    scale_step: int = 2


@dataclass
class ScalingSignalRecord:
    """Record of a scaling signal with timestamp.

    Used by IAutoscaler.enforce_cooldown() to evaluate signal history.
    """
    timestamp: float = 0.0
    signal: ScalingSignal = ScalingSignal.HOLD
    previous_count: int = 0
    target_count: int = 0
    reason: str = ""


@dataclass
class ScalingReceipt:
    """Receipt returned by a scaling action.

    Fields:
      previous_count: Worker count before scaling.
      target_count:   Requested target count.
      actual_count:   Worker count after scaling (may differ if
                      limits enforced).
      signal:         The ScalingSignal that triggered this action.
      cooldown_until: Timestamp after which next scaling is permitted.
      reason:         Human-readable reason for the scaling action.
    """
    previous_count: int = 0
    target_count: int = 0
    actual_count: int = 0
    signal: ScalingSignal = ScalingSignal.HOLD
    cooldown_until: float = 0.0
    reason: str = ""


# ════════════════════════════════════════════════════════════════════
# Health Models
# ════════════════════════════════════════════════════════════════════


@dataclass
class HealthProbeResult:
    """Result of probing a single worker's health.

    Fields:
      worker_id:  Unique worker identifier.
      alive:      True if the worker responded to the probe.
      state:      Current WorkerState.
      cpu_pct:    CPU utilization at probe time.
      mem_pct:    Memory utilization at probe time.
      last_seen:  Timestamp of last successful contact.
      latency_ms: Response latency of the probe.
    """
    worker_id: str = ""
    alive: bool = False
    state: WorkerState = WorkerState.UNKNOWN
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    last_seen: float = 0.0
    latency_ms: float = 0.0


@dataclass
class HealthEvent:
    """Event emitted when a worker's health state changes.

    Published via IHealthSupervisor.publish_health_event().

    Topics:
      - worker.health.degraded  (MINOR/MAJOR)
      - worker.health.critical  (CRITICAL)
      - worker.health.recovered (NONE after MAJOR/CRITICAL)
    """
    worker_id: str = ""
    previous_state: WorkerState = WorkerState.UNKNOWN
    current_state: WorkerState = WorkerState.UNKNOWN
    degradation: DegradationLevel = DegradationLevel.NONE
    reason: str = ""
    timestamp: float = 0.0
    event_type: HealthEventType = HealthEventType.HEALTHY


@dataclass
class EvictionReceipt:
    """Receipt from a worker eviction action.

    Fields:
      worker_id:   Evicted worker identifier.
      evicted:     True if eviction completed.
      state:       Final WorkerState (TERMINATED).
      reason:      Reason for eviction.
      leases_lost: Number of leases lost due to eviction.
    """
    worker_id: str = ""
    evicted: bool = False
    state: WorkerState = WorkerState.TERMINATED
    reason: str = ""
    leases_lost: int = 0


@dataclass
class DrainReceipt:
    """Receipt from a worker drain action.

    Fields:
      worker_id:      Drained worker identifier.
      success:        True if drain completed successfully.
      state:          Current WorkerState after drain.
      leases_released: Number of leases released during drain.
      reason:         Reason for draining.
    """
    worker_id: str = ""
    success: bool = False
    state: WorkerState = WorkerState.HEALTHY
    leases_released: int = 0
    reason: str = ""


# ════════════════════════════════════════════════════════════════════
# Cluster & Reconciliation Models
# ════════════════════════════════════════════════════════════════════


@dataclass
class ClusterSnapshot:
    """Complete snapshot of the cluster state at a point in time.

    Fields:
      worker_count:   Total workers registered.
      healthy_count:  Workers in HEALTHY state.
      degraded_count: Workers in DEGRADED state.
      draining_count: Workers in DRAINING state.
      load:           Aggregate LoadMetric for the cluster.
      timestamp:      Snapshot timestamp.
    """
    worker_count: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    draining_count: int = 0
    load: Optional[LoadMetric] = None
    timestamp: float = 0.0


@dataclass
class Correction:
    """A single correction action in the reconciliation loop.

    Fields:
      action:    Action type (e.g. "scale_up", "scale_down", "drain",
                 "terminate").
      worker_id: Target worker (empty for cluster-level actions).
      reason:    Why this correction is needed.
      priority:  Execution priority (lower = sooner).
    """
    action: str = ""
    worker_id: str = ""
    reason: str = ""
    priority: int = 5


@dataclass
class DeltaReport:
    """Report of drift between desired and actual cluster state.

    Fields:
      drift_detected:  True if any drift exists.
      worker_deficit:  Number of additional workers needed.
      worker_surplus:  Number of excess workers.
      corrections:     List of Correction objects to apply.
      observed_time:   Timestamp of observation.
    """
    drift_detected: bool = False
    worker_deficit: int = 0
    worker_surplus: int = 0
    corrections: List[Correction] = field(default_factory=list)
    observed_timestamp: float = 0.0


@dataclass
class ReconcileReport:
    """Report from a full reconciliation cycle.

    Fields:
      observed_workers:   Worker count at start of cycle.
      desired_workers:    Target worker count.
      corrections_applied: Number of corrections successfully applied.
      corrections_pending: Number of corrections still pending.
      drift_count:        Number of drift items detected.
      timestamp:          Report timestamp.
    """
    observed_workers: int = 0
    desired_workers: int = 0
    corrections_applied: int = 0
    corrections_pending: int = 0
    drift_count: int = 0
    timestamp: float = 0.0


@dataclass
class ScheduleReceipt:
    """Receipt from scheduling corrections.

    Fields:
      corrections_scheduled: Number of corrections scheduled.
      estimated_completion:  Estimated completion timestamp.
      batch_id:              Unique batch identifier.
    """
    corrections_scheduled: int = 0
    estimated_completion: float = 0.0
    batch_id: str = ""


@dataclass
class PolicyResult:
    """Result from enforcing a scaling policy.

    Fields:
      applied:        True if policy action was applied.
      signal:         Resulting ScalingSignal.
      reason:         Reason for policy decision.
      cooldown_until: Timestamp when cooldown expires.
    """
    applied: bool = False
    signal: ScalingSignal = ScalingSignal.HOLD
    reason: str = ""
    cooldown_until: float = 0.0


@dataclass
class ControlPlaneState:
    """Published state snapshot of the Control Plane (IControlPlane).

    Fields:
      active_workers:    Number of active (HEALTHY + DEGRADED) workers.
      draining_workers:  List of workers in DRAINING state.
      current_replica:   Current worker count.
      desired_replica:   Target worker count from latest evaluation.
      last_reconcile:    Timestamp of last reconciliation.
      scaling_signal:    Latest ScalingSignal.
      errors:            List of active error conditions.
    """
    active_workers: int = 0
    draining_workers: List[str] = field(default_factory=list)
    current_replica: int = 0
    desired_replica: int = 0
    last_reconcile: float = 0.0
    scaling_signal: ScalingSignal = ScalingSignal.HOLD
    errors: List[str] = field(default_factory=list)
