"""D8.1 — IExecutionRetryHandler: retry semantics only.

LAW 25: RetryHandler owns retry semantics.
FORBIDDEN: scheduling, dispatch, state, lease.

Source of Truth: core/runtime/services/retry_handler.py::ExecutionRetryHandler

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 25
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable


class RetryDecisionError(Exception):
    """Raised when retry decision cannot be computed."""


class RecordingError(Exception):
    """Raised when failure cannot be persisted."""


@runtime_checkable
class IExecutionRetryHandler(Protocol):
    """Owns retry semantics — nothing else.

    Contract methods:
      decide_retry(node_id, error, attempt, max_attempts?)  → bool
      apply_backoff(attempt, base_delay?, max_delay?)  → float
      record_failure(node_id, error, attempt, context?) → None
    """

    def decide_retry(
        self,
        node_id: str,
        error: Exception,
        attempt: int,
        max_attempts: int = 3,
    ) -> bool:
        """Decide whether a failed execution should be retried."""

    def apply_backoff(
        self,
        attempt: int,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> float:
        """Compute the backoff delay before the next retry."""

    def record_failure(
        self,
        node_id: str,
        error: Exception,
        attempt: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a failure for telemetry and pattern detection."""
