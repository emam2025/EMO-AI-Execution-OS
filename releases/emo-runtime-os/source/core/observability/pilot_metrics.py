"""Pilot Metrics — IPilotMetricsCollector for human usability validation.  # LAW-5 # LAW-12

Collects 4 human usability metrics during production pilot:
  - trust_score (1-5)
  - cognitive_load (1-10)
  - operator_error_rate (0-1)
  - time_to_first_insight (seconds)

Every metric carries pilot_trace_id and propagates through F4 Observability.

Ref: EXEC-DIRECTIVE-PILOT-001 §Task-2
Ref: Canon LAW 5, LAW 12
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PilotMetric:  # LAW-12
    pilot_trace_id: str
    metric_name: str
    value: float
    unit: str
    user_id: str
    session_id: str
    timestamp_ns: int
    task_id: str = ""


@dataclass
class PilotSession:
    session_id: str
    user_id: str
    pilot_trace_id: str
    start_ns: int
    metrics: List[PilotMetric] = field(default_factory=list)


class PilotMetricsCollector:  # LAW-5
    """Collects human usability metrics with pilot_trace_id propagation.

    LAW 5: Every metric is observable via F4 EventBus.
    LAW 12: Every metric carries pilot_trace_id for full traceability.
    RULE 4: Propagation rules P-R1–P-R6 ensure chain integrity.
    """

    def __init__(
        self,
        event_bus: Any = None,
        pilot_trace_id: str = "",
    ) -> None:
        self._trace_id = pilot_trace_id or f"pilot_{uuid.uuid4().hex[:12]}"
        self._event_bus = event_bus
        self._sessions: Dict[str, PilotSession] = {}
        self._metrics: List[PilotMetric] = []

    @property
    def pilot_trace_id(self) -> str:
        return self._trace_id

    def start_session(self, user_id: str, session_id: str = "") -> PilotSession:
        if not session_id:
            session_id = f"session_{uuid.uuid4().hex[:8]}"
        session = PilotSession(
            session_id=session_id,
            user_id=user_id,
            pilot_trace_id=self._trace_id,
            start_ns=time.time_ns(),
        )
        self._sessions[session_id] = session
        self._publish("pilot.session_start", {
            "session_id": session_id,
            "user_id": user_id,
            "pilot_trace_id": self._trace_id,
        })
        return session

    def collect_trust_score(  # LAW-5
        self,
        user_id: str,
        session_id: str,
        score: float,
    ) -> PilotMetric:
        metric = PilotMetric(
            pilot_trace_id=self._trace_id,
            metric_name="trust_score",
            value=max(1.0, min(5.0, score)),
            unit="score_1_to_5",
            user_id=user_id,
            session_id=session_id,
            timestamp_ns=time.time_ns(),
            task_id="session_end" if session_id else "general",
        )
        self._metrics.append(metric)
        self._publish("pilot.trust_score", {
            "user_id": user_id, "session_id": session_id,
            "score": metric.value, "pilot_trace_id": self._trace_id,
        })
        return metric

    def collect_cognitive_load(  # LAW-5
        self,
        user_id: str,
        task_id: str,
        load: int,
    ) -> PilotMetric:
        metric = PilotMetric(
            pilot_trace_id=self._trace_id,
            metric_name="cognitive_load",
            value=float(max(1, min(10, load))),
            unit="score_1_to_10",
            user_id=user_id,
            session_id="",
            timestamp_ns=time.time_ns(),
            task_id=task_id,
        )
        self._metrics.append(metric)
        self._publish("pilot.cognitive_load", {
            "user_id": user_id, "task_id": task_id,
            "load": metric.value, "pilot_trace_id": self._trace_id,
        })
        return metric

    def collect_operator_error_rate(  # LAW-5
        self,
        user_id: str,
        command_type: str,
        error_rate: float,
    ) -> PilotMetric:
        metric = PilotMetric(
            pilot_trace_id=self._trace_id,
            metric_name="operator_error_rate",
            value=max(0.0, min(1.0, error_rate)),
            unit="ratio",
            user_id=user_id,
            session_id="",
            timestamp_ns=time.time_ns(),
            task_id=command_type,
        )
        self._metrics.append(metric)
        self._publish("pilot.operator_error", {
            "user_id": user_id, "command_type": command_type,
            "error_rate": metric.value, "pilot_trace_id": self._trace_id,
        })
        return metric

    def collect_time_to_first_insight(  # LAW-5
        self,
        session_id: str,
        seconds: float,
    ) -> PilotMetric:
        metric = PilotMetric(
            pilot_trace_id=self._trace_id,
            metric_name="time_to_first_insight",
            value=seconds,
            unit="seconds",
            user_id="",
            session_id=session_id,
            timestamp_ns=time.time_ns(),
        )
        self._metrics.append(metric)
        self._publish("pilot.time_to_insight", {
            "session_id": session_id,
            "seconds": metric.value, "pilot_trace_id": self._trace_id,
        })
        return metric

    def get_metrics(  # LAW-12
        self,
        metric_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[PilotMetric]:
        results = list(self._metrics)
        if metric_name:
            results = [m for m in results if m.metric_name == metric_name]
        if user_id:
            results = [m for m in results if m.user_id == user_id]
        return results

    def get_average_trust_score(self) -> float:
        scores = [m.value for m in self._metrics if m.metric_name == "trust_score"]
        return sum(scores) / len(scores) if scores else 0.0

    def get_average_cognitive_load(self) -> float:
        loads = [m.value for m in self._metrics if m.metric_name == "cognitive_load"]
        return sum(loads) / len(loads) if loads else 0.0

    def get_average_operator_error_rate(self) -> float:
        rates = [m.value for m in self._metrics if m.metric_name == "operator_error_rate"]
        return sum(rates) / len(rates) if rates else 0.0

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent, EventType
            event = ExecutionEvent(
                event_id=hashlib.sha256(f"{topic}_{time.time_ns()}".encode()).hexdigest()[:16],
                event_type=EventType.STATE_TRANSITION,
                timestamp_ns=time.time_ns(),
                payload=payload,
            )
            self._event_bus.publish(topic, event)
        except Exception:
            pass
