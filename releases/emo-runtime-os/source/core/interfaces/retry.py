"""D8.1 — IExecutionRetryHandler: retry semantics only.

OWNERSHIP: retry semantics
  - retry policy evaluation
  - backoff computation
  - failure classification
  - retry exhaustion handling

FORBIDDEN:
  - scheduling
  - state storage
  - dispatch
  - lease management
"""

from typing import Any, Dict, Optional, Protocol

from core.models.dag import PlanNode, RetryPolicy


class IExecutionRetryHandler(Protocol):
    """Owns retry semantics — nothing else."""

    def classify_failure(self, error: str) -> str:
        """Classify failure type (transient, permanent, timeout, etc)."""

    def should_retry(
        self,
        node: PlanNode,
        policy: RetryPolicy,
    ) -> bool:
        """Determine if the node should be retried."""

    def compute_backoff(
        self,
        retry_count: int,
        policy: RetryPolicy,
    ) -> float:
        """Compute backoff duration for next retry."""

    def handle_exhaustion(
        self,
        node: PlanNode,
        error: str,
    ) -> Dict[str, Any]:
        """Handle retry exhaustion — final failure result."""

    def record_attempt(
        self,
        node: PlanNode,
        success: bool,
        duration: float,
    ) -> None:
        """Record a retry attempt for analytics."""
