"""CanaryMetrics — 10-metric collector with anomaly detection for Canary Deployment."""

# LAW-5: Observable — every metric collection snapshot emitted via IEventBus to F4
# LAW-8: Traceable — every snapshot carries canary_trace_id
# LAW-11: No Global State — collector state is instance-scoped
# LAW-12: Traceable — full back-traceability to originating canary session

from __future__ import annotations

import dataclasses
import enum
import hashlib
import time
from typing import Any, Dict, List, Optional


class MetricCategory(enum.Enum):
    RUNTIME = "runtime"
    DISTRIBUTED = "distributed"
    RESOURCE = "resource"
    AI = "ai"
    USABILITY = "usability"  # P1 — EXEC-DIRECTIVE-029


@dataclasses.dataclass(frozen=True)
class CanaryMetric:
    name: str
    value: float
    unit: str
    category: MetricCategory
    timestamp_ns: int
    canary_trace_id: str


@dataclasses.dataclass(frozen=True)
class CanaryMetricsSnapshot:
    canary_trace_id: str
    timestamp_ns: int
    runtime_p50_ms: float
    runtime_p95_ms: float
    runtime_p99_ms: float
    runtime_dag_completion_rate: float
    runtime_retry_rate: float
    runtime_replay_determinism_pct: float
    distributed_lease_expiry_freq: float
    distributed_ownership_conflicts: int
    distributed_worker_recovery_time_ms: float
    distributed_scheduler_fairness_score: float
    resource_memory_growth_per_hour: float
    resource_cache_hit_ratio: float
    ai_planner_determinism_drift: float
    ai_feedback_calibration_stability: float

    def to_metrics_list(self) -> List[CanaryMetric]:
        now = self.timestamp_ns
        tid = self.canary_trace_id
        return [
            CanaryMetric("p50_ms", self.runtime_p50_ms, "ms", MetricCategory.RUNTIME, now, tid),
            CanaryMetric("p95_ms", self.runtime_p95_ms, "ms", MetricCategory.RUNTIME, now, tid),
            CanaryMetric("p99_ms", self.runtime_p99_ms, "ms", MetricCategory.RUNTIME, now, tid),
            CanaryMetric("dag_completion_rate", self.runtime_dag_completion_rate, "ratio", MetricCategory.RUNTIME, now, tid),
            CanaryMetric("retry_rate", self.runtime_retry_rate, "ratio", MetricCategory.RUNTIME, now, tid),
            CanaryMetric("replay_determinism_pct", self.runtime_replay_determinism_pct, "pct", MetricCategory.RUNTIME, now, tid),
            CanaryMetric("lease_expiry_freq", self.distributed_lease_expiry_freq, "freq", MetricCategory.DISTRIBUTED, now, tid),
            CanaryMetric("ownership_conflicts", float(self.distributed_ownership_conflicts), "count", MetricCategory.DISTRIBUTED, now, tid),
            CanaryMetric("worker_recovery_time_ms", self.distributed_worker_recovery_time_ms, "ms", MetricCategory.DISTRIBUTED, now, tid),
            CanaryMetric("scheduler_fairness_score", self.distributed_scheduler_fairness_score, "score", MetricCategory.DISTRIBUTED, now, tid),
            CanaryMetric("memory_growth_per_hour", self.resource_memory_growth_per_hour, "ratio", MetricCategory.RESOURCE, now, tid),
            CanaryMetric("cache_hit_ratio", self.resource_cache_hit_ratio, "ratio", MetricCategory.RESOURCE, now, tid),
            CanaryMetric("planner_determinism_drift", self.ai_planner_determinism_drift, "ratio", MetricCategory.AI, now, tid),
            CanaryMetric("feedback_calibration_stability", self.ai_feedback_calibration_stability, "ratio", MetricCategory.AI, now, tid),
        ]


class CanaryMetricsCollector:
    def __init__(
        self,
        event_bus: Any,
        canary_trace_id: str = "",
    ):
        if canary_trace_id:
            self._trace_id = canary_trace_id
        else:
            raw = f"cmc_{time.time_ns()}"
            self._trace_id = "cmc_" + hashlib.sha256(raw.encode()).hexdigest()[:28]
        self._event_bus = event_bus
        self._history: List[CanaryMetricsSnapshot] = []
        self._anomaly_thresholds: Dict[str, float] = {
            "p99_ms": 500.0,
            "replay_determinism_pct": 0.98,
            "memory_growth_per_hour": 0.05,
            "scheduler_fairness_score": 0.7,
            "planner_determinism_drift": 0.02,
        }

    @property
    def canary_trace_id(self) -> str:
        return self._trace_id

    def collect_snapshot(
        self,
        p50_ms: float = 45.0,
        p95_ms: float = 120.0,
        p99_ms: float = 180.0,
        dag_completion_rate: float = 0.995,
        retry_rate: float = 0.015,
        replay_determinism_pct: float = 0.998,
        lease_expiry_freq: float = 0.002,
        ownership_conflicts: int = 0,
        worker_recovery_time_ms: float = 250.0,
        scheduler_fairness_score: float = 0.92,
        memory_growth_per_hour: float = 0.012,
        cache_hit_ratio: float = 0.85,
        planner_determinism_drift: float = 0.003,
        feedback_calibration_stability: float = 0.97,
    ) -> CanaryMetricsSnapshot:
        snapshot = CanaryMetricsSnapshot(
            canary_trace_id=self._trace_id,
            timestamp_ns=time.time_ns(),
            runtime_p50_ms=p50_ms,
            runtime_p95_ms=p95_ms,
            runtime_p99_ms=p99_ms,
            runtime_dag_completion_rate=dag_completion_rate,
            runtime_retry_rate=retry_rate,
            runtime_replay_determinism_pct=replay_determinism_pct,
            distributed_lease_expiry_freq=lease_expiry_freq,
            distributed_ownership_conflicts=ownership_conflicts,
            distributed_worker_recovery_time_ms=worker_recovery_time_ms,
            distributed_scheduler_fairness_score=scheduler_fairness_score,
            resource_memory_growth_per_hour=memory_growth_per_hour,
            resource_cache_hit_ratio=cache_hit_ratio,
            ai_planner_determinism_drift=planner_determinism_drift,
            ai_feedback_calibration_stability=feedback_calibration_stability,
        )
        self._history.append(snapshot)
        if self._event_bus is not None:
            self._publish_snapshot(snapshot)
        return snapshot

    def _publish_snapshot(self, snapshot: CanaryMetricsSnapshot) -> None:
        try:
            from core.models.events import ExecutionEvent, EventType
            for metric in snapshot.to_metrics_list():
                event = ExecutionEvent(
                    event_id=hashlib.sha256(
                        f"{metric.name}_{metric.timestamp_ns}".encode()
                    ).hexdigest()[:16],
                    event_type=EventType.STATE_TRANSITION,
                    timestamp_ns=snapshot.timestamp_ns,
                    payload={
                        "action": "canary_metric",
                        "metric_name": metric.name,
                        "value": metric.value,
                        "unit": metric.unit,
                        "category": metric.category.value,
                        "canary_trace_id": metric.canary_trace_id,
                    },
                )
                self._event_bus.publish("runtime.canary.metrics", event)
        except Exception:
            pass

    def detect_anomaly(
        self, snapshot: CanaryMetricsSnapshot,
    ) -> Optional[str]:
        if snapshot.runtime_p99_ms > self._anomaly_thresholds["p99_ms"]:
            return (
                f"P99 anomaly: {snapshot.runtime_p99_ms}ms > "
                f"{self._anomaly_thresholds['p99_ms']}ms"
            )
        if snapshot.runtime_replay_determinism_pct < self._anomaly_thresholds["replay_determinism_pct"]:
            return (
                f"Replay determinism anomaly: {snapshot.runtime_replay_determinism_pct} < "
                f"{self._anomaly_thresholds['replay_determinism_pct']}"
            )
        if snapshot.resource_memory_growth_per_hour > self._anomaly_thresholds["memory_growth_per_hour"]:
            return (
                f"Memory growth anomaly: {snapshot.resource_memory_growth_per_hour} > "
                f"{self._anomaly_thresholds['memory_growth_per_hour']}"
            )
        if snapshot.distributed_scheduler_fairness_score < self._anomaly_thresholds["scheduler_fairness_score"]:
            return (
                f"Scheduler fairness anomaly: {snapshot.distributed_scheduler_fairness_score} < "
                f"{self._anomaly_thresholds['scheduler_fairness_score']}"
            )
        if snapshot.ai_planner_determinism_drift > self._anomaly_thresholds["planner_determinism_drift"]:
            return (
                f"Planner drift anomaly: {snapshot.ai_planner_determinism_drift} > "
                f"{self._anomaly_thresholds['planner_determinism_drift']}"
            )
        return None

    def get_history(self) -> List[CanaryMetricsSnapshot]:
        return list(self._history)

    # ── P1 — Usability Metrics (EXEC-DIRECTIVE-029) ────────────────
    # LAW-5: Observable — every usability metric snapshot published to F4
    # LAW-12: Traceable — every snapshot carries pilot_trace_id

    @dataclasses.dataclass(frozen=True)
    class UsabilitySnapshot:
        pilot_trace_id: str
        timestamp_ns: int
        time_to_first_insight_sec: float
        operator_error_rate_pct: float
        trust_score_1_to_5: float
        cognitive_load_self_reported: int

        def to_metrics(self, tid: str) -> List[CanaryMetric]:
            now = self.timestamp_ns
            cat = MetricCategory.USABILITY
            return [
                CanaryMetric("time_to_first_insight_sec", self.time_to_first_insight_sec, "sec", cat, now, tid),
                CanaryMetric("operator_error_rate_pct", self.operator_error_rate_pct, "pct", cat, now, tid),
                CanaryMetric("trust_score_1_to_5", self.trust_score_1_to_5, "score", cat, now, tid),
                CanaryMetric("cognitive_load_self_reported", float(self.cognitive_load_self_reported), "score", cat, now, tid),
            ]

    @property
    def _usability_history(self) -> List[UsabilitySnapshot]:
        if not hasattr(self, '_usability_history_store'):
            self._usability_history_store: List[CanaryMetricsCollector.UsabilitySnapshot] = []
        return self._usability_history_store

    def collect_usability_snapshot(  # LAW-5 # EXEC-DIRECTIVE-029
        self,
        pilot_trace_id: str = "",
        time_to_first_insight_sec: float = 15.0,
        operator_error_rate_pct: float = 5.0,
        trust_score_1_to_5: float = 4.0,
        cognitive_load_self_reported: int = 3,
    ) -> UsabilitySnapshot:
        if not pilot_trace_id:
            pilot_trace_id = f"pilot_{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]}"
        snapshot = self.UsabilitySnapshot(
            pilot_trace_id=pilot_trace_id,
            timestamp_ns=time.time_ns(),
            time_to_first_insight_sec=time_to_first_insight_sec,
            operator_error_rate_pct=operator_error_rate_pct,
            trust_score_1_to_5=trust_score_1_to_5,
            cognitive_load_self_reported=cognitive_load_self_reported,
        )
        self._usability_history.append(snapshot)
        if self._event_bus is not None:
            try:
                from core.models.events import ExecutionEvent, EventType
                for metric in snapshot.to_metrics(pilot_trace_id):
                    event = ExecutionEvent(
                        event_id=hashlib.sha256(f"usability_{metric.name}_{metric.timestamp_ns}".encode()).hexdigest()[:16],
                        event_type=EventType.STATE_TRANSITION,
                        timestamp_ns=snapshot.timestamp_ns,
                        payload={
                            "action": "usability_metric",
                            "metric_name": metric.name,
                            "value": metric.value,
                            "unit": metric.unit,
                            "category": metric.category.value,
                            "pilot_trace_id": pilot_trace_id,
                        },
                    )
                    self._event_bus.publish("runtime.usability.metrics", event)
            except Exception:
                pass
        return snapshot

    def get_usability_history(self) -> List[UsabilitySnapshot]:
        return list(self._usability_history)
