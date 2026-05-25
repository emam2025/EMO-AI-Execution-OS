"""Phase F2 — Control Plane & Autoscaler: Formal Protocol Definitions.

This file defines 4 typing.Protocol classes that form the contract
for the Phase F2 Control Plane architecture:

  1. IControlPlane         — Top-level orchestrator
  2. IAutoscaler            — Scaling decision engine
  3. IHealthSupervisor      — Worker health & eviction
  4. IReconciliationLoop    — Observe→Compare→Act cycle

All protocols follow ROADMAP Phase F2 and DEVELOPER.md §15.9.
Oscillation prevention (Cooldown/Hysteresis) is mandatory per §15.9.4.

Ref: Canon LAW 5 (Observability), LAW 8 (State transitions), LAW 11 (No global state)
Ref: RULE 1 (Determinism), RULE 2 (Reversibility), RULE 3 (Recoverability),
     RULE 4 (Terminal states), RULE 5 (Idempotency)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


# ════════════════════════════════════════════════════════════════════
# Shared types (must match models/02_scaling_and_health_models.py)
# ════════════════════════════════════════════════════════════════════


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


@dataclass
class LoadMetric:
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    queue_depth: int = 0
    avg_latency_ms: float = 0.0
    active_leases: int = 0


@dataclass
class ScalingPolicy:
    min_workers: int = 1
    max_workers: int = 32
    target_utilization: float = 0.70
    cooldown_sec: float = 60.0
    hysteresis_pct: float = 0.10
    scale_step: int = 2


@dataclass
class ClusterSnapshot:
    worker_count: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    draining_count: int = 0
    load: Optional[LoadMetric] = None
    timestamp: float = 0.0


@dataclass
class ScalingReceipt:
    previous_count: int = 0
    target_count: int = 0
    actual_count: int = 0
    signal: ScalingSignal = ScalingSignal.HOLD
    cooldown_until: float = 0.0
    reason: str = ""


@dataclass
class DrainReceipt:
    worker_id: str = ""
    success: bool = False
    state: WorkerState = WorkerState.HEALTHY
    leases_released: int = 0
    reason: str = ""


@dataclass
class HealthProbeResult:
    worker_id: str = ""
    alive: bool = False
    state: WorkerState = WorkerState.UNKNOWN
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    last_seen: float = 0.0
    latency_ms: float = 0.0


@dataclass
class ReconcileReport:
    observed_workers: int = 0
    desired_workers: int = 0
    corrections_applied: int = 0
    corrections_pending: int = 0
    drift_count: int = 0
    timestamp: float = 0.0


@dataclass
class Correction:
    action: str = ""
    worker_id: str = ""
    reason: str = ""
    priority: int = 0


@dataclass
class PolicyResult:
    applied: bool = False
    signal: ScalingSignal = ScalingSignal.HOLD
    reason: str = ""
    cooldown_until: float = 0.0


# ════════════════════════════════════════════════════════════════════
# 1. IControlPlane
# ════════════════════════════════════════════════════════════════════


@runtime_checkable
class IControlPlane(Protocol):
    """Top-level orchestrator for the F2 Control Plane.

    Owns the reconciliation loop, delegates scaling decisions to
    IAutoscaler, and manages worker lifecycle (drain, terminate).

    LAW 8: All state transitions MUST be guarded.
    LAW 11: No global state — per-instance.
    RULE 5: All operations are idempotent.
    """

    def reconcile(self, desired_state: ClusterSnapshot) -> ReconcileReport:
        """Run one reconciliation cycle.

        Compares observed cluster state against desired_state,
        computes delta, and applies corrections.

        Args:
            desired_state: Target cluster configuration.

        Returns:
            ReconcileReport with drift and correction stats.
        """
        ...

    def enforce_policy(
        self,
        policy: ScalingPolicy,
        context: ClusterSnapshot,
    ) -> PolicyResult:
        """Enforce a scaling policy against the current context.

        Evaluates whether a scaling action is permitted given
        cooldown, resource limits, and worker availability.

        Args:
            policy: Active scaling policy.
            context: Current cluster snapshot.

        Returns:
            PolicyResult with action and cooldown info.
        """
        ...

    def publish_state(self) -> ControlPlaneState:
        """Publish the current Control Plane state snapshot.

        Returns:
            ControlPlaneState with all metrics and status.
        """
        ...

    def drain_worker(self, worker_id: str, reason: str = "") -> DrainReceipt:
        """Initiate graceful drain of a worker.

        Draining lifecycle:
          MARK_DRAINING → STOP_NEW_LEASES → AWAIT_COMPLETION
          → RELEASE_LEASES → TERMINATE

        Each step MUST be idempotent (RULE 5).

        Args:
            worker_id: Target worker identifier.
            reason: Reason for draining.

        Returns:
            DrainReceipt with result and released lease count.
        """
        ...


@dataclass
class ControlPlaneState:
    """Published state snapshot of the Control Plane."""
    active_workers: int = 0
    draining_workers: List[str] = field(default_factory=list)
    current_replica: int = 0
    desired_replica: int = 0
    last_reconcile: float = 0.0
    scaling_signal: ScalingSignal = ScalingSignal.HOLD
    errors: List[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
# 2. IAutoscaler
# ════════════════════════════════════════════════════════════════════


@runtime_checkable
class IAutoscaler(Protocol):
    """Scaling decision engine.

    Evaluates load metrics against policy thresholds and produces
    oscillation-free scaling signals.

    §15.9.4: Cooldown and hysteresis are mandatory.
    LAW 5: All decisions observable.
    RULE 1: Deterministic — same load + policy → same signal.
    """

    def evaluate_load(
        self,
        snapshot: ClusterSnapshot,
        policy: ScalingPolicy,
    ) -> ScalingSignal:
        """Evaluate current load and return a scaling signal.

        Guards:
          - UP requires utilization > target + hysteresis for 2 cycles
          - DOWN requires utilization < target - hysteresis for 2 cycles
          - HOLD if within hysteresis band or cooldown active

        Args:
            snapshot: Current cluster load snapshot.
            policy: Active scaling policy.

        Returns:
            ScalingSignal: UP, DOWN, HOLD, or DRAIN.
        """
        ...

    def calculate_target_count(
        self,
        load_snapshot: LoadMetric,
        policy: ScalingPolicy,
    ) -> int:
        """Calculate the desired worker count based on load.

        Formula:
          target = ceil(current * utilization / target_utilization)

        Clamped to [policy.min_workers, policy.max_workers].

        Args:
            load_snapshot: Current load metrics.
            policy: Active scaling policy.

        Returns:
            Desired worker count.
        """
        ...

    def apply_scaling(
        self,
        target_count: int,
        policy: ScalingPolicy,
        current_workers: int = 0,
    ) -> ScalingReceipt:
        """Apply a scaling action to reach target_count.

        Uses scale_step for incremental changes.

        Args:
            target_count: Desired worker count.
            policy: Active scaling policy.
            current_workers: Current active worker count.

        Returns:
            ScalingReceipt with actual vs target.
        """
        ...

    def enforce_cooldown(
        self,
        signal_history: List[Tuple[float, ScalingSignal]],
        policy: ScalingPolicy,
    ) -> bool:
        """Check if cooldown period has expired.

        Cooldown starts after any UP or DOWN action.
        HOLD and DRAIN do not reset cooldown.

        Args:
            signal_history: Chronological signal list.
            policy: Active scaling policy.

        Returns:
            True if cooldown expired and scaling is permitted.
        """
        ...


# ════════════════════════════════════════════════════════════════════
# 3. IHealthSupervisor
# ════════════════════════════════════════════════════════════════════


class DegradationLevel(str, Enum):
    """Progressive degradation levels for worker health."""
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


@dataclass
class HealthEvent:
    """Event emitted for health status changes."""
    worker_id: str = ""
    previous_state: WorkerState = WorkerState.UNKNOWN
    current_state: WorkerState = WorkerState.UNKNOWN
    degradation: DegradationLevel = DegradationLevel.NONE
    reason: str = ""
    timestamp: float = 0.0


@dataclass
class EvictionReceipt:
    worker_id: str = ""
    evicted: bool = False
    state: WorkerState = WorkerState.TERMINATED
    reason: str = ""
    leases_lost: int = 0


@runtime_checkable
class IHealthSupervisor(Protocol):
    """Worker health monitoring and eviction.

    Probes workers at configurable intervals, assesses degradation,
    and triggers eviction for critically degraded workers.

    LAW 5: All health events observable.
    LAW 11: No global state — per-instance.
    RULE 3: Degraded workers are recoverable.
    """

    def probe_worker(self, worker_id: str) -> HealthProbeResult:
        """Probe a single worker's health.

        Returns:
            HealthProbeResult with alive status, resource usage.
        """
        ...

    def assess_degradation(
        self,
        worker_id: str,
        probe: HealthProbeResult,
    ) -> DegradationLevel:
        """Assess degradation level from probe results.

        Classification:
          - alive, cpu < 80%, mem < 80% → NONE
          - alive, cpu > 80% or mem > 80% → MINOR
          - alive, cpu > 95% or mem > 95% → MAJOR
          - not alive or latency > threshold → CRITICAL

        Args:
            worker_id: Target worker.
            probe: Latest health probe result.

        Returns:
            DegradationLevel.
        """
        ...

    def trigger_eviction(
        self,
        worker_id: str,
        reason: str = "",
    ) -> EvictionReceipt:
        """Trigger eviction of a critically degraded worker.

        Eviction preconditions:
          - DegradationLevel == CRITICAL
          - Worker is not already DRAINING or TERMINATED

        Eviction always initiates drain first, then terminates.

        Args:
            worker_id: Target worker.
            reason: Reason for eviction.

        Returns:
            EvictionReceipt.
        """
        ...

    def publish_health_event(self, event: HealthEvent) -> None:
        """Publish a health event to EventBus.

        Topics:
          - worker.health.degraded (MINOR/MAJOR)
          - worker.health.critical (CRITICAL)
          - worker.health.recovered (NONE after MAJOR/CRITICAL)

        Args:
            event: HealthEvent to publish.
        """
        ...


# ════════════════════════════════════════════════════════════════════
# 4. IReconciliationLoop
# ════════════════════════════════════════════════════════════════════


@dataclass
class DeltaReport:
    """Report of drift between desired and actual state."""
    drift_detected: bool = False
    worker_deficit: int = 0
    worker_surplus: int = 0
    corrections: List[Correction] = field(default_factory=list)
    observed_timestamp: float = 0.0


@dataclass
class ScheduleReceipt:
    corrections_scheduled: int = 0
    estimated_completion: float = 0.0
    batch_id: str = ""


@runtime_checkable
class IReconciliationLoop(Protocol):
    """Observe → Compare → Act cycle.

    Runs at configurable intervals to ensure cluster state matches
    the desired configuration.

    Interval strategy (per §15.9.2):
      - observe: every 5s
      - evaluate: every 15s
      - act: every 30s

    RULE 1: Deterministic comparison.
    RULE 2: Corrections are reversible.
    """

    def observe_current(self) -> ClusterSnapshot:
        """Collect the current cluster state.

        Returns:
            ClusterSnapshot with worker counts and load metrics.
        """
        ...

    def compare_desired(
        self,
        actual: ClusterSnapshot,
        desired: ClusterSnapshot,
    ) -> DeltaReport:
        """Compare actual state against desired state.

        Computes drift as:
          drift = actual.worker_count - desired.worker_count
          deficit = max(0, desired - actual)
          surplus = max(0, actual - desired)

        Args:
            actual: Observed cluster snapshot.
            desired: Target cluster snapshot.

        Returns:
            DeltaReport with drift and corrections.
        """
        ...

    def compute_delta(
        self,
        actual: ClusterSnapshot,
        desired: ClusterSnapshot,
    ) -> List[Correction]:
        """Compute the list of corrections needed.

        Each correction targets a specific worker and action.

        Args:
            actual: Observed cluster snapshot.
            desired: Target cluster snapshot.

        Returns:
            List of Correction objects.
        """
        ...

    def schedule_correction(
        self,
        corrections: List[Correction],
    ) -> ScheduleReceipt:
        """Schedule corrections for execution.

        Corrections are batched and executed in priority order.

        Args:
            corrections: List of corrections to apply.

        Returns:
            ScheduleReceipt with batch info.
        """
        ...
