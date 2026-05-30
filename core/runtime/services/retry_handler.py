"""D8.1 — ExecutionRetryHandler: retry semantics (LAW 25).

LAW 25: RetryHandler owns retry semantics.
FORBIDDEN: scheduling, dispatch, state, lease.

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 25
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("emo_ai.services.retry_handler")


class RetryDecisionError(Exception):
    """Raised when retry decision cannot be computed."""


class RecordingError(Exception):
    """Raised when failure cannot be persisted."""


class ExecutionRetryHandler:
    """Retry semantics service — owns retry decision, backoff, failure recording.

    LAW 25: RetryHandler owns retry semantics.
    Private state: _failure_counts, _backoff_state, _pattern_store.
    No access to scheduler, dispatcher, state_store, or lease_manager state.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 25
    """

    def __init__(self) -> None:
        self._failure_counts: Dict[str, int] = {}
        self._backoff_state: Dict[str, float] = {}
        self._pattern_store: Dict[str, Any] = {}

    def decide_retry(
        self,
        node_id: str,
        error: Exception,
        attempt: int,
        max_attempts: int = 3,
    ) -> bool:
        """Decide whether a failed execution should be retried.

        LAW 25: Only RetryHandler may decide retry semantics.

        Args:
            node_id: The failed node's identifier.
            error: The exception that caused the failure.
            attempt: Current attempt number (1-indexed).
            max_attempts: Maximum allowed attempts.

        Returns:
            True if retry should proceed, False if failure is terminal.

        Raises:
            RetryDecisionError: If retry decision cannot be computed.
        """
        try:
            if attempt > max_attempts:
                logger.info(
                    "Max attempts reached for %s (%d/%d)",
                    node_id, attempt, max_attempts,
                )
                return False

            # Never retry terminal errors
            terminal_types = (
                "ValueError", "TypeError", "ContractViolationError",
                "UnknownToolError", "CapabilityViolation",
            )
            error_type = type(error).__name__
            if error_type in terminal_types:
                logger.info("Terminal error %s for %s — no retry", error_type, node_id)
                return False

            # Check circuit breaker
            count = self._failure_counts.get(node_id, 0)
            if count >= max_attempts:
                logger.warning("Circuit open for %s — no retry", node_id)
                return False

            logger.debug("Retry decision YES for %s (attempt %d)", node_id, attempt)
            return True

        except Exception as e:
            raise RetryDecisionError(
                f"Cannot compute retry decision for node {node_id}: {e}"
            ) from e

    def apply_backoff(
        self,
        attempt: int,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> float:
        """Compute the backoff delay before the next retry.

        LAW 25: Only RetryHandler may compute backoff.
        Uses exponential backoff with jitter.

        Args:
            attempt: Current attempt number.
            base_delay: Base delay in seconds.
            max_delay: Maximum delay cap in seconds.

        Returns:
            Delay in seconds before next retry attempt.
        """
        if attempt <= 1:
            delay = base_delay
        else:
            delay = base_delay * (2 ** (attempt - 1))

        # Add jitter (±20%)
        jitter = random.uniform(-0.2, 0.2) * delay
        delay = min(delay + jitter, max_delay)

        return max(0.1, delay)

    def record_failure(
        self,
        node_id: str,
        error: Exception,
        attempt: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a failure for telemetry and pattern detection.

        LAW 25: Only RetryHandler may record failures.

        Args:
            node_id: The failed node's identifier.
            error: The exception that occurred.
            attempt: Attempt number when failure occurred.
            context: Optional metadata about the failure.

        Raises:
            RecordingError: If failure cannot be persisted.
        """
        try:
            self._failure_counts[node_id] = self._failure_counts.get(node_id, 0) + 1
            self._pattern_store[node_id] = {
                "error": str(error),
                "error_type": type(error).__name__,
                "attempt": attempt,
                "timestamp": time.time(),
                "context": context or {},
            }
            logger.debug(
                "Recorded failure for %s (attempt %d, total %d)",
                node_id, attempt, self._failure_counts[node_id],
            )
        except Exception as e:
            raise RecordingError(
                f"Cannot persist failure for node {node_id}: {e}"
            ) from e
