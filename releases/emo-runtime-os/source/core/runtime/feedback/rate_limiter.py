"""D9 — Rate Limiter for Feedback Loop.

Tracks adjustment/alert frequency per scope per hour.
LAW 11: No global state — per-instance rate limiting.

Ref: DEVELOPER.md §5.3, §5.4
Ref: Canon LAW 11
Ref: artifacts/design/d9/03_drift_feedback_state_machine.md §5
"""

from __future__ import annotations

import time
from typing import Dict, List


class RateLimiter:
    """Tracks adjustment/alert frequency per scope.

    Ref: §5.4 — Cooldown & Rate Limiting
    """

    def __init__(self) -> None:
        self._adjustments: Dict[str, List[float]] = {}
        self._alerts: Dict[str, List[float]] = {}
        self._last_cooldown: Dict[str, float] = {}

    def can_adjust(self, scope: str, max_per_hour: int = 3) -> bool:
        """Check if an adjustment is allowed for the given scope.

        Args:
            scope: Scope identifier (node_id or component name).
            max_per_hour: Maximum adjustments per hour.

        Returns:
            True if within rate limit.
        """
        now = time.time()
        recent = [
            t for t in self._adjustments.get(scope, [])
            if t > now - 3600
        ]
        return len(recent) < max_per_hour

    def record_adjustment(self, scope: str) -> None:
        """Record a successful adjustment for rate tracking."""
        if scope not in self._adjustments:
            self._adjustments[scope] = []
        self._adjustments[scope].append(time.time())
        self._last_cooldown[scope] = time.time()

    def can_alert(self, node_id: str, max_per_hour: int = 6) -> bool:
        """Check if an alert is allowed for the given node.

        Args:
            node_id: Node identifier.
            max_per_hour: Maximum alerts per hour.

        Returns:
            True if within rate limit.
        """
        now = time.time()
        recent = [
            t for t in self._alerts.get(node_id, [])
            if t > now - 3600
        ]
        return len(recent) < max_per_hour

    def record_alert(self, node_id: str) -> None:
        """Record an alert for rate tracking."""
        if node_id not in self._alerts:
            self._alerts[node_id] = []
        self._alerts[node_id].append(time.time())

    def cooldown_remaining(self, scope: str, cooldown_seconds: float = 1200.0) -> float:
        """Get remaining cooldown time in seconds for a scope.

        Args:
            scope: Scope identifier.
            cooldown_seconds: Cooldown period in seconds (default 20 min).

        Returns:
            Seconds remaining (0 if no cooldown active).
        """
        last = self._last_cooldown.get(scope, 0.0)
        elapsed = time.time() - last
        return max(0.0, cooldown_seconds - elapsed)

    def is_in_cooldown(self, scope: str, cooldown_seconds: float = 1200.0) -> bool:
        """Check if a scope is in cooldown.

        Args:
            scope: Scope identifier.
            cooldown_seconds: Cooldown period in seconds.

        Returns:
            True if in cooldown.
        """
        return self.cooldown_remaining(scope, cooldown_seconds) > 0.0

    def reset(self) -> None:
        """Reset all rate limits (for testing)."""
        self._adjustments.clear()
        self._alerts.clear()
        self._last_cooldown.clear()
