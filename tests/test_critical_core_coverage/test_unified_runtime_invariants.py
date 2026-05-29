"""High-signal tests for UnifiedRuntime API — constants, guards, error types.

Tests target exposed invariants that work without constructing the full runtime.
"""

import pytest

from core.runtime.api.unified_runtime_api import MAX_WORKER_COUNT
from core.runtime.api.unified_runtime_api import (
    SubmissionRejected,
    InvalidStateTransition,
    ScaleLimitExceeded,
    WorkerRegistrationFailed,
)


class TestUnifiedRuntimeConstants:
    """Invariant: scaling limits and error types are defined."""

    def test_max_worker_count_is_256(self):
        """MAX_WORKER_COUNT must be 256 (hard limit)."""
        assert MAX_WORKER_COUNT == 256, (
            f"Expected MAX_WORKER_COUNT=256, got {MAX_WORKER_COUNT}"
        )


class TestUnifiedRuntimeErrorTypes:
    """Invariant: all error types are importable and chain correctly."""

    def test_submission_rejected_is_exception(self):
        """SubmissionRejected must be a valid exception."""
        assert issubclass(SubmissionRejected, Exception)

    def test_invalid_state_transition_is_exception(self):
        """InvalidStateTransition must be a valid exception."""
        assert issubclass(InvalidStateTransition, Exception)

    def test_scale_limit_exceeded_is_exception(self):
        """ScaleLimitExceeded must be a valid exception."""
        assert issubclass(ScaleLimitExceeded, Exception)

    def test_worker_registration_failed_is_exception(self):
        """WorkerRegistrationFailed must be a valid exception."""
        assert issubclass(WorkerRegistrationFailed, Exception)
