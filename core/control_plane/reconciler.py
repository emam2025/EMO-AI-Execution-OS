"""F2 — Reconciliation Loop with anti-loop, circuit breaker, deduplication.

The reconciler continuously:
   1. Reads desired state (what SHOULD be)
   2. Reads actual state from SystemStateBrain (what IS)
   3. Computes diff
   4. Produces corrections with anti-loop protection

Improvements over 6.2:
  - Circuit breaker: stops issuing corrections for targets that keep failing
  - Deduplication: identical corrections are suppressed in the same cycle
  - Cooldowns: each target+action pair gets a cooldown period
  - Max corrections per cycle: safety limit
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core.control_plane.state.system_state import SystemStateBrain

logger = logging.getLogger("emo_ai.control_plane.reconciler")


@dataclass
class DesiredState:
    """What the system SHOULD look like."""
    min_workers: int = 2
    max_workers: int = 20
    max_worker_cpu: float = 0.80
    max_worker_error_rate: float = 0.05
    max_execution_retries: int = 3
    max_node_latency_ms: float = 500.0
    heartbeat_timeout_seconds: float = 30.0
    cooldown_seconds: float = 30.0
    max_corrections_per_cycle: int = 20
    circuit_breaker_threshold: int = 5


@dataclass
class Correction:
    """A single correction action from the reconciler."""
    action: str
    reason: str
    target_id: str = ""
    priority: int = 0  # 0 = critical, 1 = high, 2 = normal
    payload: Dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        """Unique key for deduplication."""
        return f"{self.action}:{self.target_id}"


class Reconciler:
    """Self-healing reconciliation loop with stability controls.

    Features:
      - Circuit breaker: tracks repeated failed corrections per target
      - Deduplication: suppresses identical corrections in one cycle
      - Cooldown: enforces minimum time between corrections for same target+action
      - Max corrections: safety limit per cycle
    """

    def __init__(self, desired: Optional[DesiredState] = None):
        self._desired = desired or DesiredState()
        self._attempts: Dict[str, int] = defaultdict(int)
        self._last_correction_time: Dict[str, float] = {}
        self._circuit_open: Set[str] = set()

    @property
    def desired(self) -> DesiredState:
        return self._desired

    def reset_circuit_breaker(self, target_key: str) -> None:
        """Manually reset circuit breaker for a target."""
        self._circuit_open.discard(target_key)
        self._attempts[target_key] = 0

    def reset_all(self) -> None:
        """Reset all circuit breakers and cooldowns."""
        self._attempts.clear()
        self._last_correction_time.clear()
        self._circuit_open.clear()

    def _correction_key(self, action: str, target_id: str) -> str:
        return f"{action}:{target_id}"

    def _is_circuit_open(self, action: str, target_id: str) -> bool:
        ck = self._correction_key(action, target_id)
        return ck in self._circuit_open

    def _record_attempt(self, action: str, target_id: str) -> None:
        ck = self._correction_key(action, target_id)
        self._attempts[ck] += 1
        self._last_correction_time[ck] = time.time()
        if self._attempts[ck] >= self._desired.circuit_breaker_threshold:
            self._circuit_open.add(ck)
            logger.warning("Circuit breaker opened for %s (attempts=%d)",
                           ck, self._attempts[ck])

    def _in_cooldown(self, action: str, target_id: str) -> bool:
        ck = self._correction_key(action, target_id)
        last = self._last_correction_time.get(ck, 0.0)
        return (time.time() - last) < self._desired.cooldown_seconds

    def record_correction_outcome(self, action: str, target_id: str,
                                   succeeded: bool) -> None:
        """Record whether a correction succeeded.

        On success, resets the attempt counter.
        On failure, increments the attempt counter.
        """
        ck = self._correction_key(action, target_id)
        if succeeded:
            self._attempts[ck] = 0
            self._circuit_open.discard(ck)
        else:
            self._record_attempt(action, target_id)

    def reconcile(self, state: SystemStateBrain) -> List[Correction]:
        """Run one reconciliation cycle with stability controls.

        Args:
            state: The current system state (truth model).

        Returns:
            List of corrections to apply (empty if all suppressed).
        """
        all_corrections: List[Correction] = []
        now = time.time()

        # 1. Check dead workers
        for wid, worker in state.all_workers().items():
            action = "restart_worker"
            age = now - worker.last_heartbeat
            if age > self._desired.heartbeat_timeout_seconds:
                all_corrections.append(Correction(
                    action=action,
                    reason=f"Worker {wid} heartbeat timeout ({age:.0f}s)",
                    target_id=wid,
                    priority=0,
                    payload={"worker_id": wid, "node_id": worker.node_id},
                ))

        # 2. Check worker count (scale up/down)
        healthy = len(state.healthy_workers())
        if healthy < self._desired.min_workers:
            needed = self._desired.min_workers - healthy
            all_corrections.append(Correction(
                action="scale_up",
                reason=f"Healthy workers ({healthy}) < min ({self._desired.min_workers})",
                priority=1,
                payload={"count": needed},
            ))
        elif healthy > self._desired.max_workers:
            excess = healthy - self._desired.max_workers
            all_corrections.append(Correction(
                action="scale_down",
                reason=f"Healthy workers ({healthy}) > max ({self._desired.max_workers})",
                priority=2,
                payload={"count": excess},
            ))

        # 3. Check overloaded workers
        for wid, worker in state.all_workers().items():
            if worker.active_tasks >= worker.capacity:
                all_corrections.append(Correction(
                    action="redistribute_load",
                    reason=f"Worker {wid} at capacity ({worker.active_tasks}/{worker.capacity})",
                    target_id=wid,
                    priority=1,
                    payload={"worker_id": wid, "active_tasks": worker.active_tasks},
                ))

        # 4. Check failed nodes
        for nid, node in state.all_nodes().items():
            if node.status == "down":
                worker_count = len(state.workers_by_node(nid))
                all_corrections.append(Correction(
                    action="blacklist_node",
                    reason=f"Node {nid} is down with {worker_count} workers",
                    target_id=nid,
                    priority=0,
                    payload={"node_id": nid, "worker_count": worker_count},
                ))

        # 5. Check stuck executions
        for ex in state.active_executions():
            if ex.started_at > 0 and (now - ex.started_at) > 300:
                all_corrections.append(Correction(
                    action="migrate_execution",
                    reason=f"Execution {ex.execution_id} running too long ({now - ex.started_at:.0f}s)",
                    target_id=ex.execution_id,
                    priority=1,
                    payload={
                        "execution_id": ex.execution_id,
                        "worker_id": ex.worker_id,
                    },
                ))

        # 6. Check retry escalation
        for eid, ex in state.all_executions().items():
            if ex.retry_count >= self._desired.max_execution_retries:
                all_corrections.append(Correction(
                    action="escalate_retry",
                    reason=f"Execution {eid} retried {ex.retry_count} times",
                    target_id=eid,
                    priority=0,
                    payload={
                        "execution_id": eid,
                        "retry_count": ex.retry_count,
                    },
                ))

        # ── Filter: deduplication ──────────────────────────────
        seen: Set[str] = set()
        deduped: List[Correction] = []
        for c in all_corrections:
            k = c.key()
            if k not in seen:
                seen.add(k)
                deduped.append(c)

        # ── Filter: circuit breaker + cooldown ─────────────────
        final: List[Correction] = []
        for c in deduped:
            if self._is_circuit_open(c.action, c.target_id):
                logger.debug("Suppressed %s: circuit open", c.key())
                continue
            if self._in_cooldown(c.action, c.target_id):
                logger.debug("Suppressed %s: in cooldown", c.key())
                continue
            final.append(c)

        # ── Safety limit ───────────────────────────────────────
        if len(final) > self._desired.max_corrections_per_cycle:
            logger.warning("Reconciler: truncating %d → %d corrections",
                           len(final), self._desired.max_corrections_per_cycle)
            final.sort(key=lambda c: c.priority)
            final = final[:self._desired.max_corrections_per_cycle]

        # ── Record attempts ────────────────────────────────────
        for c in final:
            self._record_attempt(c.action, c.target_id)

        if final:
            logger.info("Reconciler: %d corrections (%d raw, %d deduped)",
                         len(final), len(all_corrections), len(deduped))
            for c in final:
                logger.debug("  [%d] %s: %s", c.priority, c.action, c.reason)

        return final
