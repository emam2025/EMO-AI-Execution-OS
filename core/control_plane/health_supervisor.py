"""F2 — HealthSupervisor: advanced health monitoring + auto-recovery.

Extends HealthManager with:
  - Proactive health probes (not just passive heartbeat tracking)
  - Auto-recovery actions (restart unhealthy workers)
  - Escalation policies (notify, quarantine, terminate)
  - Health check configuration per service/node type
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("emo_ai.control_plane.health_supervisor")


class RecoveryAction(Enum):
    RESTART = "restart"
    QUARANTINE = "quarantine"
    ESCALATE = "escalate"
    NOTIFY = "notify"
    IGNORE = "ignore"


@dataclass
class HealthCheckConfig:
    interval_seconds: float = 15.0
    timeout_seconds: float = 5.0
    max_failures: int = 3
    recovery_action: RecoveryAction = RecoveryAction.RESTART
    cooldown_seconds: float = 60.0


@dataclass
class ProbeResult:
    target_id: str
    alive: bool
    latency_ms: float = 0.0
    error: str = ""
    timestamp: float = 0.0


@dataclass
class RecoveryOperation:
    target_id: str
    action: RecoveryAction
    started_at: float = 0.0
    completed_at: float = 0.0
    success: bool = False
    error: str = ""


class HealthSupervisor:
    """Advanced health monitoring with auto-recovery.

    Separates health checking (passive via HealthManager)
    from proactive probing and recovery (this class).
    """

    def __init__(self,
                 probe_fn: Optional[Callable[[str], ProbeResult]] = None,
                 recovery_fn: Optional[Callable[[str, RecoveryAction], bool]] = None):
        self._configs: Dict[str, HealthCheckConfig] = {}
        self._failure_counts: Dict[str, int] = {}
        self._last_probe: Dict[str, float] = {}
        self._recoveries: List[RecoveryOperation] = []
        self._probe_fn = probe_fn
        self._recovery_fn = recovery_fn
        self._quarantined: set[str] = set()

    def set_config(self, target_id: str,
                   config: Optional[HealthCheckConfig] = None) -> None:
        self._configs[target_id] = config or HealthCheckConfig()

    def get_config(self, target_id: str) -> HealthCheckConfig:
        return self._configs.get(target_id, HealthCheckConfig())

    def probe(self, target_id: str) -> ProbeResult:
        """Probe a target's health actively.

        Uses the configured probe function, or returns a default
        alive result if no probe is configured.
        """
        now = time.time()
        self._last_probe[target_id] = now

        if not self._probe_fn:
            return ProbeResult(
                target_id=target_id,
                alive=True,
                timestamp=now,
            )

        try:
            return self._probe_fn(target_id)
        except Exception as e:
            return ProbeResult(
                target_id=target_id,
                alive=False,
                error=str(e),
                timestamp=now,
            )

    def record_failure(self, target_id: str) -> int:
        """Record a failure and return current failure count."""
        self._failure_counts[target_id] = self._failure_counts.get(target_id, 0) + 1
        return self._failure_counts[target_id]

    def record_success(self, target_id: str) -> None:
        """Reset failure count on success."""
        self._failure_counts[target_id] = 0

    def assess(self, target_id: str) -> RecoveryAction:
        """Assess a target and return the recommended action.

        Args:
            target_id: The target to assess.

        Returns:
            The recommended recovery action.
        """
        config = self.get_config(target_id)
        failures = self._failure_counts.get(target_id, 0)

        if target_id in self._quarantined:
            return RecoveryAction.QUARANTINE

        if failures >= config.max_failures:
            action = config.recovery_action
            self._execute_recovery(target_id, action)
            return action

        if failures > 0:
            return RecoveryAction.NOTIFY

        return RecoveryAction.IGNORE

    def tick(self) -> List[RecoveryAction]:
        """Run health check cycle for all registered targets.

        Probes each target, records results, and triggers recovery actions.
        """
        actions: List[RecoveryAction] = []
        for target_id in list(self._configs.keys()):
            config = self.get_config(target_id)
            now = time.time()
            last = self._last_probe.get(target_id, 0.0)
            if now - last < config.interval_seconds:
                continue

            result = self.probe(target_id)
            if result.alive:
                self.record_success(target_id)
            else:
                failures = self.record_failure(target_id)
                logger.warning("Probe failed for %s (%d/%d): %s",
                               target_id, failures, config.max_failures, result.error)
                if failures >= config.max_failures:
                    action = self.assess(target_id)
                    actions.append(action)

        return actions

    def _execute_recovery(self, target_id: str, action: RecoveryAction) -> None:
        """Execute the recovery action for a target."""
        op = RecoveryOperation(
            target_id=target_id,
            action=action,
            started_at=time.time(),
        )
        try:
            if self._recovery_fn:
                op.success = self._recovery_fn(target_id, action)
            else:
                op.success = True
            if action == RecoveryAction.QUARANTINE:
                self._quarantined.add(target_id)
        except Exception as e:
            op.success = False
            op.error = str(e)
        op.completed_at = time.time()
        self._recoveries.append(op)
        logger.info("Recovery: %s → %s (success=%s)", target_id, action.value, op.success)

    def quarantine(self, target_id: str) -> None:
        self._quarantined.add(target_id)

    def unquarantine(self, target_id: str) -> None:
        self._quarantined.discard(target_id)
        self._failure_counts[target_id] = 0

    def is_quarantined(self, target_id: str) -> bool:
        return target_id in self._quarantined

    def recovery_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [
            {
                "target": op.target_id,
                "action": op.action.value,
                "success": op.success,
                "error": op.error,
                "duration": round(op.completed_at - op.started_at, 3) if op.completed_at > 0 else 0,
            }
            for op in self._recoveries[-limit:]
        ]

    def clear_failures(self, target_id: str) -> None:
        self._failure_counts[target_id] = 0
