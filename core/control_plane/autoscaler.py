"""F2 — Autoscaler: independent scaling controller.

Separate from the reconciler. Makes scaling decisions based on:
  - Queue depth (pending tasks)
  - Worker utilization (CPU/memory averages)
  - Saturation (active_tasks / capacity ratio)
  - Time-based scheduling (predictive)

Does NOT execute scaling — produces recommendations.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.control_plane.autoscaler")


class ScalingDirection(Enum):
    UP = "up"
    DOWN = "down"
    NONE = "none"


@dataclass
class ScalingDecision:
    direction: ScalingDirection
    count: int = 0
    reason: str = ""
    confidence: float = 1.0


@dataclass
class AutoscalerConfig:
    min_workers: int = 2
    max_workers: int = 50
    scale_up_threshold: float = 0.70
    scale_down_threshold: float = 0.30
    cooldown_seconds: float = 60.0
    scale_up_step: int = 2
    scale_down_step: int = 1
    cpu_target: float = 0.65
    memory_target: float = 0.70


class Autoscaler:
    """Independent autoscaling controller.

    Monitors system metrics and produces scaling recommendations.
    Does NOT execute scaling — that's the RuntimeOS/Coordinator's job.
    """

    def __init__(self, config: Optional[AutoscalerConfig] = None):
        self._config = config or AutoscalerConfig()
        self._last_scale_time: float = 0.0
        self._history: List[Dict[str, Any]] = []

    @property
    def config(self) -> AutoscalerConfig:
        return self._config

    # ── Scaling Signals ─────────────────────────────────────

    def evaluate(self, current_workers: int,
                 pending_tasks: int = 0,
                 worker_utilization: float = 0.0,
                 _request_rate: float = 0.0) -> ScalingDecision:
        """Evaluate whether to scale and produce a decision.

        Args:
            current_workers: Current number of active workers.
            pending_tasks: Number of tasks waiting in queue.
            worker_utilization: Average worker utilization (0.0–1.0).
            request_rate: Incoming request rate (tasks/sec).

        Returns:
            ScalingDecision with direction, count, and reason.
        """
        now = time.time()
        in_cooldown = (now - self._last_scale_time) < self._config.cooldown_seconds

        scaling_signals: List[str] = []

        # Signal 1: Worker count bounds
        if current_workers >= self._config.max_workers:
            return ScalingDecision(ScalingDirection.NONE, 0, "At max workers")
        if current_workers <= self._config.min_workers:
            pass  # Don't auto-scale-down below min

        # Signal 2: Utilization-based
        if worker_utilization >= self._config.scale_up_threshold:
            scaling_signals.append(f"high_utilization({worker_utilization:.2f})")
        elif worker_utilization <= self._config.scale_down_threshold:
            if current_workers > self._config.min_workers:
                scaling_signals.append(f"low_utilization({worker_utilization:.2f})")

        # Signal 3: Pending tasks
        if pending_tasks > 0:
            tasks_per_worker = pending_tasks / max(1, current_workers)
            if tasks_per_worker > 3:
                scaling_signals.append(f"pending_tasks({pending_tasks})")

        if not scaling_signals:
            return ScalingDecision(ScalingDirection.NONE, 0, "No scaling signals")

        # Decide direction
        is_up = any("high_utilization" in s or "pending_tasks" in s for s in scaling_signals)
        is_down = any("low_utilization" in s for s in scaling_signals)

        # Cooldown check
        if in_cooldown:
            remaining = self._config.cooldown_seconds - (now - self._last_scale_time)
            return ScalingDecision(
                ScalingDirection.NONE, 0,
                f"Cooldown ({remaining:.0f}s remaining)",
            )

        if is_up and not is_down:
            count = self._config.scale_up_step
            if pending_tasks > 10:
                count = min(count * 2, self._config.max_workers - current_workers)
            direction = ScalingDirection.UP
            reason = "; ".join(scaling_signals)
        elif is_down and not is_up:
            count = min(self._config.scale_down_step,
                        current_workers - self._config.min_workers)
            direction = ScalingDirection.DOWN
            reason = "; ".join(scaling_signals)
        else:
            return ScalingDecision(ScalingDirection.NONE, 0, "Conflicting signals")

        decision = ScalingDecision(direction, count, reason)
        self._history.append({
            "timestamp": now,
            "decision": direction.value,
            "count": count,
            "reason": reason,
            "current_workers": current_workers,
            "utilization": worker_utilization,
            "pending": pending_tasks,
        })
        return decision

    def record_scaling(self, direction: ScalingDirection) -> None:
        """Record that a scaling action was executed (for cooldown)."""
        self._last_scale_time = time.time()
        logger.info("Autoscaler: recorded scale %s", direction.value)

    def scaling_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._history[-limit:]

    def reset_cooldown(self) -> None:
        self._last_scale_time = 0.0
