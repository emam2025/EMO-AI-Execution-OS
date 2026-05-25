"""Phase F2 — Health Supervisor implementation.

Implements IHealthSupervisor: probes workers, assesses degradation,
triggers eviction, publishes health events to EventBus.

Ref: Canon LAW 5 (Observability), LAW 11 (No global state), RULE 3 (Recoverability)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional

from core.runtime.models.control_plane_models import (
    DegradationLevel,
    EvictionReceipt,
    HealthEvent,
    HealthEventType,
    HealthProbeResult,
    WorkerState,
)

logger = logging.getLogger("emo_ai.control_plane.health")


class HealthSupervisor:  # ←→ IHealthSupervisor
    """Monitors worker health, classifies degradation, and triggers eviction.

    LAW 5: All health events observable via EventBus.
    LAW 11: No global state — per-instance worker tracking.
    RULE 3: Degraded workers can recover (MINOR/MAJOR → NONE).
    """

    CPU_MINOR_THRESHOLD: float = 80.0
    CPU_MAJOR_THRESHOLD: float = 95.0
    MEM_MINOR_THRESHOLD: float = 80.0
    MEM_MAJOR_THRESHOLD: float = 95.0
    LATENCY_CRITICAL_THRESHOLD: float = 5000.0

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._event_bus = event_bus
        self._worker_states: Dict[str, WorkerState] = {}
        self._degradation_levels: Dict[str, DegradationLevel] = {}

    # ── probe_worker ──────────────────────────────────────────

    def probe_worker(  # LAW-5
        self,
        worker_id: str,
    ) -> HealthProbeResult:
        alive = worker_id in self._worker_states
        state = self._worker_states.get(worker_id, WorkerState.UNKNOWN)
        deg = self._degradation_levels.get(worker_id, DegradationLevel.NONE)

        return HealthProbeResult(
            worker_id=worker_id,
            alive=alive,
            state=state,
            cpu_pct=0.0,
            mem_pct=0.0,
            last_seen=time.time() if alive else 0.0,
            latency_ms=0.0,
        )

    def update_worker_health(
        self,
        worker_id: str,
        state: WorkerState,
        cpu_pct: float = 0.0,
        mem_pct: float = 0.0,
        latency_ms: float = 0.0,
    ) -> None:
        self._worker_states[worker_id] = state
        probe = HealthProbeResult(
            worker_id=worker_id,
            alive=state != WorkerState.UNKNOWN,
            state=state,
            cpu_pct=cpu_pct,
            mem_pct=mem_pct,
            last_seen=time.time(),
            latency_ms=latency_ms,
        )
        deg = self.assess_degradation(worker_id, probe)
        prev_deg = self._degradation_levels.get(worker_id, DegradationLevel.NONE)
        self._degradation_levels[worker_id] = deg

        if deg != prev_deg:
            event_type = self._classify_event_type(prev_deg, deg)
            event = HealthEvent(
                worker_id=worker_id,
                previous_state=state,
                current_state=state,
                degradation=deg,
                reason=f"degradation: {prev_deg.value} → {deg.value}",
                timestamp=time.time(),
                event_type=event_type,
            )
            self.publish_health_event(event)

    # ── assess_degradation ────────────────────────────────────

    def assess_degradation(  # LAW-5, RULE-3
        self,
        worker_id: str,
        probe: HealthProbeResult,
    ) -> DegradationLevel:
        if not probe.alive or probe.latency_ms > self.LATENCY_CRITICAL_THRESHOLD:
            return DegradationLevel.CRITICAL

        cpu = probe.cpu_pct
        mem = probe.mem_pct

        if cpu > self.CPU_MAJOR_THRESHOLD or mem > self.MEM_MAJOR_THRESHOLD:
            return DegradationLevel.MAJOR

        if cpu > self.CPU_MINOR_THRESHOLD or mem > self.MEM_MINOR_THRESHOLD:
            return DegradationLevel.MINOR

        return DegradationLevel.NONE

    # ── trigger_eviction ──────────────────────────────────────

    def trigger_eviction(  # LAW-8, RULE-5
        self,
        worker_id: str,
        reason: str = "",
    ) -> EvictionReceipt:
        current_state = self._worker_states.get(worker_id, WorkerState.UNKNOWN)
        current_deg = self._degradation_levels.get(worker_id, DegradationLevel.NONE)

        if current_state in (WorkerState.DRAINING, WorkerState.TERMINATED):
            return EvictionReceipt(
                worker_id=worker_id,
                evicted=False,
                state=current_state,
                reason=f"already {current_state.value}",
                leases_lost=0,
            )

        if current_deg != DegradationLevel.CRITICAL:
            return EvictionReceipt(
                worker_id=worker_id,
                evicted=False,
                state=current_state,
                reason=f"degradation {current_deg.value} < CRITICAL",
                leases_lost=0,
            )

        self._worker_states[worker_id] = WorkerState.TERMINATED
        self._degradation_levels[worker_id] = DegradationLevel.NONE

        event = HealthEvent(
            worker_id=worker_id,
            previous_state=current_state,
            current_state=WorkerState.TERMINATED,
            degradation=DegradationLevel.CRITICAL,
            reason=reason or "evicted: critical degradation",
            timestamp=time.time(),
            event_type=HealthEventType.CRITICAL,
        )
        self.publish_health_event(event)

        return EvictionReceipt(
            worker_id=worker_id,
            evicted=True,
            state=WorkerState.TERMINATED,
            reason=reason or "evicted: critical degradation",
            leases_lost=0,
        )

    # ── publish_health_event ──────────────────────────────────

    def publish_health_event(  # LAW-5
        self,
        event: HealthEvent,
    ) -> None:
        if self._event_bus is None:
            logger.debug("No event bus: %s %s", event.event_type.value, event.worker_id)
            return

        topic = event.event_type.value
        try:
            from core.models.events import ExecutionEvent
            bus_event = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type=event.event_type.value,
                timestamp=event.timestamp,
                source="HealthSupervisor",
                payload={
                    "worker_id": event.worker_id,
                    "previous_state": event.previous_state.value,
                    "current_state": event.current_state.value,
                    "degradation": event.degradation.value,
                    "reason": event.reason,
                },
            )
            self._event_bus.publish(topic, bus_event)
        except Exception as e:
            logger.error("Failed to publish health event: %s", e)

    def _classify_event_type(
        self,
        prev: DegradationLevel,
        current: DegradationLevel,
    ) -> HealthEventType:
        if prev in (DegradationLevel.MAJOR, DegradationLevel.CRITICAL) and current == DegradationLevel.NONE:
            return HealthEventType.RECOVERED
        if current == DegradationLevel.CRITICAL:
            return HealthEventType.CRITICAL
        if current in (DegradationLevel.MINOR, DegradationLevel.MAJOR):
            return HealthEventType.DEGRADED
        return HealthEventType.HEALTHY
