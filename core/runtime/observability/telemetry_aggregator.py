"""Phase F4 — TelemetryAggregator implementation.  # LAW-5 # LAW-12

Implements ITelemetryAggregator: ingest_event, compute_metrics,
flush_window, publish_summary.

LAW 5: Every critical span MUST be accounted for.
LAW 11: No global state — per-instance buffer.
RULE 3: On flush failure, preserve buffer for retry.

Ref: Canon LAW 5 (Observability), LAW 12 (Traceability), RULE 3
Ref: artifacts/design/f4/protocols/01_observability_protocols.py::ITelemetryAggregator
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

from core.runtime.models.observability_models import (
    AggregatedMetric,
    AggregationSummary,
    Severity,
    TelemetryEventType,
    WindowStrategy,
)
from core.runtime.observability.aggregation_state_machine import (
    AggregationState,
    AggregationStateMachine,
)
from core.runtime.observability.backpressure_sampler import BackpressureSampler

logger = logging.getLogger("emo_ai.observability.telemetry_aggregator")


class TelemetryAggregator:  # ←→ ITelemetryAggregator  # LAW-5
    """Concrete implementation of ITelemetryAggregator.

    Ingests raw telemetry events, buffers by window, computes
    aggregated metrics, and publishes summaries to EventBus.

    Backpressure: adaptive_sampling() never drops CRITICAL spans.
    """

    def __init__(
        self,
        state_machine: Optional[AggregationStateMachine] = None,
        sampler: Optional[BackpressureSampler] = None,
    ) -> None:
        self._sm = state_machine or AggregationStateMachine()
        self._sampler = sampler or BackpressureSampler()
        self._buffer: Dict[str, List[Tuple[TelemetryEventType, Dict[str, str], Optional[str]]]] = {}
        self._flushed_summaries: Dict[str, AggregationSummary] = {}
        self._published_keys: set = set()

    @property
    def state_machine(self) -> AggregationStateMachine:
        return self._sm

    @property
    def sampler(self) -> BackpressureSampler:
        return self._sampler

    @property
    def buffer_snapshot(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self._buffer.items()}

    # ── ingest_event ────────────────────────────────────────────

    def ingest_event(  # LAW-5, RULE-5
        self,
        event_type: TelemetryEventType,
        payload: Dict[str, str],
        trace_id: Optional[str] = None,
    ) -> None:
        window_key = self._resolve_window_key(event_type, trace_id)

        self._sm.transition(AggregationState.VALIDATED)
        self._sm.transition(AggregationState.BUFFERED)

        if window_key not in self._buffer:
            self._buffer[window_key] = []

        self._buffer[window_key].append((event_type, payload, trace_id))
        logger.debug("Ingested %s into window %s", event_type.value, window_key)

    # ── compute_metrics ─────────────────────────────────────────

    def compute_metrics(  # LAW-5, RULE-1
        self,
        window_key: str,
        strategy: WindowStrategy = WindowStrategy.TUMBLING_1M,
    ) -> AggregationSummary:
        events = self._buffer.get(window_key, [])
        if not events:
            return AggregationSummary(window_key=window_key)

        self._sm.transition(AggregationState.AGGREGATING)
        self._sm.transition(AggregationState.COMPUTED)

        total = len(events)
        alerts = sum(1 for e, _, _ in events if e == TelemetryEventType.ALERT_FIRED)
        errors = sum(
            1 for e, p, _ in events
            if e == TelemetryEventType.SPAN_END and p.get("status") == "error"
        )

        metric = AggregatedMetric(
            metric_name=f"events.{strategy.value}",
            window_key=window_key,
            count=total,
        )

        return AggregationSummary(
            window_key=window_key,
            span_count=total,
            alert_count=alerts,
            error_count=errors,
            metrics=[metric],
            dropped_count=self._sampler.dropped_count,
            lag_ms=0.0,
        )

    # ── flush_window ────────────────────────────────────────────

    def flush_window(  # RULE-3
        self,
        window_key: str,
    ) -> AggregationSummary:
        summary = self.compute_metrics(window_key)

        self._sm.transition(AggregationState.FLUSHING)

        self._flushed_summaries[window_key] = summary
        if window_key in self._buffer:
            del self._buffer[window_key]

        self._sm.transition(AggregationState.PERSISTED)

        logger.info("Flushed window %s (%d events)", window_key, summary.span_count)
        return summary

    # ── publish_summary ─────────────────────────────────────────

    def publish_summary(  # LAW-5
        self,
        summary: AggregationSummary,
        event_bus_publish=None,
    ) -> None:
        if summary.window_key in self._published_keys:
            logger.debug("Summary %s already published (idempotent)", summary.window_key)
            return

        self._published_keys.add(summary.window_key)

        if event_bus_publish:
            event_bus_publish("runtime.telemetry.summary", summary)

        logger.info("Published summary for window %s", summary.window_key)

    # ── reset (testing) ─────────────────────────────────────────

    def reset(self) -> None:
        self._buffer.clear()
        self._flushed_summaries.clear()
        self._published_keys.clear()
        self._sampler.reset()

    @staticmethod
    def _resolve_window_key(
        event_type: TelemetryEventType,
        trace_id: Optional[str],
    ) -> str:
        if trace_id:
            return f"session:{trace_id}"
        now_s = int(time.time())
        return f"tumbling:{now_s - (now_s % 60)}"
