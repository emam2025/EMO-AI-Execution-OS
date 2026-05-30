"""CanaryObserver — ICanaryObserver protocol for canary session monitoring."""

# LAW-5: Observable — metrics collection and anomaly detection via IEventBus
# LAW-8: Traceable — every snapshot carries canary_trace_id
# LAW-11: No Global State — observer state is instance-scoped
# LAW-12: Traceable — full back-traceability from metrics to canary_trace_id

from __future__ import annotations

import dataclasses
import enum
import hashlib
import time
from typing import Any, Dict, List, Optional, Protocol


class AnomalySeverity(enum.Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


@dataclasses.dataclass(frozen=True)
class CanaryMetricSnapshot:
    canary_trace_id: str
    user_id: str
    timestamp_ns: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    dag_completion_rate: float
    retry_rate: float
    replay_determinism_pct: float
    lease_expiry_freq: float
    ownership_conflicts: int
    worker_recovery_time_ms: float
    scheduler_fairness_score: float
    memory_growth_per_hour: float
    cache_hit_ratio: float
    planner_determinism_drift: float
    feedback_calibration_stability: float

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class AnomalyReport:
    snapshot_id: str
    user_id: str
    severity: AnomalySeverity
    metric_name: str
    observed_value: float
    threshold: float
    message: str
    timestamp_ns: int
    canary_trace_id: str


class ICanaryObserver(Protocol):
    def collect_metrics(self, user_id: str) -> CanaryMetricSnapshot:
        ...

    def detect_anomaly(
        self, snapshot: CanaryMetricSnapshot
    ) -> Optional[AnomalyReport]:
        ...

    def trigger_alert(self, report: AnomalyReport) -> None:
        ...


class CanaryObserver:
    _instance_counter: int = 0

    def __init__(
        self,
        event_bus: Any,
        canary_trace_id: str = "",
    ):
        CanaryObserver._instance_counter += 1
        if canary_trace_id:
            self._trace_id = canary_trace_id
        else:
            raw = f"canary_{time.time_ns()}_{CanaryObserver._instance_counter}"
            self._trace_id = "cny_" + hashlib.sha256(
                raw.encode()
            ).hexdigest()[:28]
        self._event_bus = event_bus
        self._alert_history: List[AnomalyReport] = []
        self._metric_history: List[CanaryMetricSnapshot] = []

    @property
    def canary_trace_id(self) -> str:
        return self._trace_id

    def collect_metrics(self, user_id: str) -> CanaryMetricSnapshot:
        # Simulate metric collection — in production, this reads from runtime
        snapshot = CanaryMetricSnapshot(
            canary_trace_id=self._trace_id,
            user_id=user_id,
            timestamp_ns=time.time_ns(),
            p50_ms=45.0,
            p95_ms=120.0,
            p99_ms=180.0,
            dag_completion_rate=0.995,
            retry_rate=0.015,
            replay_determinism_pct=0.998,
            lease_expiry_freq=0.002,
            ownership_conflicts=0,
            worker_recovery_time_ms=250.0,
            scheduler_fairness_score=0.92,
            memory_growth_per_hour=0.012,
            cache_hit_ratio=0.85,
            planner_determinism_drift=0.003,
            feedback_calibration_stability=0.97,
        )
        self._metric_history.append(snapshot)
        return snapshot

    def detect_anomaly(
        self, snapshot: CanaryMetricSnapshot,
    ) -> Optional[AnomalyReport]:
        # P99 latency check
        if snapshot.p99_ms > 500.0:
            return AnomalyReport(
                snapshot_id=hashlib.sha256(
                    str(time.time_ns()).encode()
                ).hexdigest()[:12],
                user_id=snapshot.user_id,
                severity=AnomalySeverity.FATAL,
                metric_name="p99_ms",
                observed_value=snapshot.p99_ms,
                threshold=500.0,
                message=f"P99 latency {snapshot.p99_ms}ms exceeds 500ms threshold",
                timestamp_ns=snapshot.timestamp_ns,
                canary_trace_id=self._trace_id,
            )
        # Replay determinism check
        if snapshot.replay_determinism_pct < 0.98:
            return AnomalyReport(
                snapshot_id=hashlib.sha256(
                    str(time.time_ns()).encode()
                ).hexdigest()[:12],
                user_id=snapshot.user_id,
                severity=AnomalySeverity.FATAL,
                metric_name="replay_determinism_pct",
                observed_value=snapshot.replay_determinism_pct,
                threshold=0.98,
                message=f"Replay determinism {snapshot.replay_determinism_pct}% below 98%",
                timestamp_ns=snapshot.timestamp_ns,
                canary_trace_id=self._trace_id,
            )
        # Memory growth check
        if snapshot.memory_growth_per_hour > 0.05:
            return AnomalyReport(
                snapshot_id=hashlib.sha256(
                    str(time.time_ns()).encode()
                ).hexdigest()[:12],
                user_id=snapshot.user_id,
                severity=AnomalySeverity.FATAL,
                metric_name="memory_growth_per_hour",
                observed_value=snapshot.memory_growth_per_hour,
                threshold=0.05,
                message=f"Memory growth {snapshot.memory_growth_per_hour*100}%/hour exceeds 5% threshold",
                timestamp_ns=snapshot.timestamp_ns,
                canary_trace_id=self._trace_id,
            )
        # Lease conflict check
        if snapshot.lease_expiry_freq > 0.0 and snapshot.ownership_conflicts > 0:
            return AnomalyReport(
                snapshot_id=hashlib.sha256(
                    str(time.time_ns()).encode()
                ).hexdigest()[:12],
                user_id=snapshot.user_id,
                severity=AnomalySeverity.CRITICAL,
                metric_name="lease_conflict_count",
                observed_value=float(snapshot.ownership_conflicts),
                threshold=0.0,
                message=f"Lease conflict detected: {snapshot.ownership_conflicts} conflicts",
                timestamp_ns=snapshot.timestamp_ns,
                canary_trace_id=self._trace_id,
            )
        # Scheduler fairness check
        if snapshot.scheduler_fairness_score < 0.7:
            return AnomalyReport(
                snapshot_id=hashlib.sha256(
                    str(time.time_ns()).encode()
                ).hexdigest()[:12],
                user_id=snapshot.user_id,
                severity=AnomalySeverity.CRITICAL,
                metric_name="scheduler_fairness_score",
                observed_value=snapshot.scheduler_fairness_score,
                threshold=0.7,
                message=f"Scheduler fairness {snapshot.scheduler_fairness_score} below 0.7",
                timestamp_ns=snapshot.timestamp_ns,
                canary_trace_id=self._trace_id,
            )
        # Planner determinism drift check
        if snapshot.planner_determinism_drift > 0.02:
            return AnomalyReport(
                snapshot_id=hashlib.sha256(
                    str(time.time_ns()).encode()
                ).hexdigest()[:12],
                user_id=snapshot.user_id,
                severity=AnomalySeverity.WARNING,
                metric_name="planner_determinism_drift",
                observed_value=snapshot.planner_determinism_drift,
                threshold=0.02,
                message=f"Planner drift {snapshot.planner_determinism_drift*100}% exceeds 2%",
                timestamp_ns=snapshot.timestamp_ns,
                canary_trace_id=self._trace_id,
            )
        return None

    def trigger_alert(self, report: AnomalyReport) -> None:
        self._alert_history.append(report)
        if self._event_bus is not None:
            try:
                from core.models.events import ExecutionEvent, EventType
                event = ExecutionEvent(
                    event_id=report.snapshot_id,
                    event_type=EventType.STATE_TRANSITION,
                    timestamp_ns=report.timestamp_ns,
                    payload={
                        "action": "canary_alert",
                        "user_id": report.user_id,
                        "metric": report.metric_name,
                        "observed": report.observed_value,
                        "threshold": report.threshold,
                        "severity": report.severity.value,
                        "message": report.message,
                        "canary_trace_id": report.canary_trace_id,
                    },
                )
                self._event_bus.publish("runtime.canary.alerts", event)
                self._event_bus.publish("runtime.readiness.canary", event)
            except Exception:
                pass

    def get_alert_history(self) -> List[AnomalyReport]:
        return list(self._alert_history)

    def get_metric_history(self) -> List[CanaryMetricSnapshot]:
        return list(self._metric_history)
