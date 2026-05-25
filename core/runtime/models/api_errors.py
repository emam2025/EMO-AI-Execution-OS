"""F1 — Error Taxonomy & Response Envelope.

Implements the error hierarchy from artifacts/design/f1/models/03_error_taxonomy_models.py.
Maps every error to a Canon Law reference.

LAW 8: All errors have defined recovery.
LAW 12: All errors carry trace_id.
RULE 4: Errors trigger cleanup (killable).

Ref: DEVELOPER.md §15.2, §15.3
Ref: Canon LAW 8, LAW 12, RULE 4
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


class ErrorCategory(str, Enum):
    VALIDATION = "validation"
    RESOURCE = "resource"
    STATE = "state"
    LEASE = "lease"
    WORKER = "worker"
    REPLAY = "replay"
    INTERNAL = "internal"
    SECURITY = "security"


class ErrorSeverity(str, Enum):
    FATAL = "fatal"
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ErrorCode(str, Enum):
    SUBMISSION_REJECTED = "SUBMISSION_REJECTED"
    CHECKPOINT_MISSING = "CHECKPOINT_MISSING"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    LEASE_CONFLICT = "LEASE_CONFLICT"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    WORKER_UNAVAILABLE = "WORKER_UNAVAILABLE"
    WORKER_REGISTRATION_FAILED = "WORKER_REGISTRATION_FAILED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    REPLAY_MISMATCH = "REPLAY_MISMATCH"
    REPLAY_TRACE_INCOMPLETE = "REPLAY_TRACE_INCOMPLETE"
    SCALE_FAILED = "SCALE_FAILED"
    SCALE_LIMIT_EXCEEDED = "SCALE_LIMIT_EXCEEDED"

    # Runtime execution errors
    TICKET_NOT_FOUND = "TICKET_NOT_FOUND"
    EXECUTION_UNKNOWN = "EXECUTION_UNKNOWN"


class APIError(Exception):
    """Base error for all Unified Runtime API errors.

    LAW 12: All errors carry trace_id for cross-layer correlation.
    LAW 8: recoverable flag indicates retry viability.
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str = "",
        trace_id: str = "",
        recoverable: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.error_code = error_code
        self.trace_id = trace_id
        self.recoverable = recoverable
        self.details = details or {}
        super().__init__(f"[{error_code.value}] {message}")


class SubmissionRejected(APIError):
    """LAW 1: DAG validation failed."""
    def __init__(self, message: str = "", trace_id: str = "", errors: Optional[List[str]] = None):
        super().__init__(ErrorCode.SUBMISSION_REJECTED, message, trace_id, True,
                         {"validation_errors": errors or []})


class CheckpointMissing(APIError):
    """LAW 4/8: No checkpoint found for resume."""
    def __init__(self, message: str = "", trace_id: str = ""):
        super().__init__(ErrorCode.CHECKPOINT_MISSING, message, trace_id, False)


class InvalidStateTransition(APIError):
    """LAW 8: State transition violates state machine rules."""
    def __init__(self, message: str = "", trace_id: str = "",
                 current_state: str = "", target_state: str = ""):
        super().__init__(ErrorCode.INVALID_STATE_TRANSITION, message, trace_id, True,
                         {"current_state": current_state, "target_state": target_state})


class LeaseConflict(APIError):
    """LAW 3: Lease already held by another owner."""
    def __init__(self, message: str = "", trace_id: str = "", current_owner: str = ""):
        super().__init__(ErrorCode.LEASE_CONFLICT, message, trace_id, True,
                         {"current_owner": current_owner})


class QuotaExceeded(APIError):
    """LAW 10: Resource cap reached."""
    def __init__(self, message: str = "", trace_id: str = "",
                 resource: str = "", limit: float = 0.0, current: float = 0.0):
        super().__init__(ErrorCode.QUOTA_EXCEEDED, message, trace_id, True,
                         {"resource": resource, "limit": limit, "current": current})


class WorkerUnavailable(APIError):
    """LAW 10: No worker available."""
    def __init__(self, message: str = "", trace_id: str = "",
                 worker_id: str = "", required_capability: str = ""):
        super().__init__(ErrorCode.WORKER_UNAVAILABLE, message, trace_id, True,
                         {"worker_id": worker_id, "required_capability": required_capability})


class ExecutionTimeout(APIError):
    """RULE 4: Node execution exceeded timeout."""
    def __init__(self, message: str = "", trace_id: str = "",
                 node_id: str = "", timeout: float = 0.0, elapsed: float = 0.0):
        super().__init__(ErrorCode.EXECUTION_TIMEOUT, message, trace_id, True,
                         {"node_id": node_id, "timeout": timeout, "elapsed": elapsed})


class ReplayMismatch(APIError):
    """LAW 4/7: Replay output differs from original."""
    def __init__(self, message: str = "", trace_id: str = "",
                 original_hash: str = "", replay_hash: str = ""):
        super().__init__(ErrorCode.REPLAY_MISMATCH, message, trace_id, False,
                         {"original_hash": original_hash, "replay_hash": replay_hash})


class RollbackFailed(APIError):
    """LAW 8: Rollback of partial state failed."""
    def __init__(self, message: str = "", trace_id: str = "",
                 node_id: str = "", reason: str = ""):
        super().__init__(ErrorCode.ROLLBACK_FAILED, message, trace_id, False,
                         {"node_id": node_id, "reason": reason})


class ScaleError(APIError):
    """LAW 10: Worker pool scaling operation failed."""
    def __init__(self, message: str = "", trace_id: str = "",
                 target: int = 0, actual: int = 0):
        super().__init__(ErrorCode.SCALE_FAILED, message, trace_id, True,
                         {"target": target, "actual": actual})


class ScaleLimitExceeded(APIError):
    """LAW 10: Target worker count exceeds system maximum."""
    def __init__(self, message: str = "", trace_id: str = "",
                 target: int = 0, maximum: int = 0):
        super().__init__(ErrorCode.SCALE_LIMIT_EXCEEDED, message, trace_id, True,
                         {"target": target, "maximum": maximum})


class WorkerRegistrationFailed(APIError):
    """§15.4: Worker manifest invalid or endpoint unreachable."""
    def __init__(self, message: str = "", trace_id: str = "", worker_id: str = ""):
        super().__init__(ErrorCode.WORKER_REGISTRATION_FAILED, message, trace_id, True,
                         {"worker_id": worker_id})


class TicketNotFound(APIError):
    """No execution found for the given ticket_id."""
    def __init__(self, message: str = "", trace_id: str = "", ticket_id: str = ""):
        super().__init__(ErrorCode.TICKET_NOT_FOUND, message, trace_id, False,
                         {"ticket_id": ticket_id})


@dataclass
class ResponseEnvelope(Generic[T]):
    """Standard response envelope for all Unified Runtime API calls.

    LAW 5 enforcement: Every response is observable with trace_id.
    LAW 12 enforcement: Every response carries trace_id + timestamp.
    """

    ticket_id: str
    status: str
    data: Optional[T] = None
    error: Optional[APIError] = None
    trace_id: str = ""
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()

    @classmethod
    def success(cls, data: T, ticket_id: str = "", trace_id: str = "",
                timestamp: float = 0.0) -> ResponseEnvelope[T]:
        return cls(
            ticket_id=ticket_id,
            status="success",
            data=data,
            trace_id=trace_id,
            timestamp=timestamp or time.time(),
        )

    @classmethod
    def error(cls, error: APIError, ticket_id: str = "",
              trace_id: str = "", timestamp: float = 0.0) -> ResponseEnvelope[T]:
        return cls(
            ticket_id=ticket_id,
            status="error",
            error=error,
            trace_id=trace_id or error.trace_id,
            timestamp=timestamp or time.time(),
        )

    @classmethod
    def pending(cls, ticket_id: str, trace_id: str = "",
                timestamp: float = 0.0) -> ResponseEnvelope[T]:
        return cls(
            ticket_id=ticket_id,
            status="pending",
            trace_id=trace_id,
            timestamp=timestamp or time.time(),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ticket_id": self.ticket_id,
            "status": self.status,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
        }
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = {
                "code": self.error.error_code.value,
                "message": str(self.error),
                "trace_id": self.error.trace_id,
                "recoverable": self.error.recoverable,
                "details": self.error.details,
            }
        return result


ERROR_CODE_LAW_MAP: Dict[ErrorCode, str] = {
    ErrorCode.SUBMISSION_REJECTED: "LAW 1",
    ErrorCode.CHECKPOINT_MISSING: "LAW 4, LAW 8",
    ErrorCode.INVALID_STATE_TRANSITION: "LAW 8",
    ErrorCode.LEASE_CONFLICT: "LAW 3",
    ErrorCode.LEASE_EXPIRED: "LAW 3, LAW 10",
    ErrorCode.QUOTA_EXCEEDED: "LAW 10",
    ErrorCode.WORKER_UNAVAILABLE: "LAW 10",
    ErrorCode.WORKER_REGISTRATION_FAILED: "LAW 10, §15.4",
    ErrorCode.EXECUTION_TIMEOUT: "RULE 4",
    ErrorCode.EXECUTION_FAILED: "LAW 10",
    ErrorCode.ROLLBACK_FAILED: "LAW 8",
    ErrorCode.REPLAY_MISMATCH: "LAW 4, LAW 7",
    ErrorCode.REPLAY_TRACE_INCOMPLETE: "LAW 4",
    ErrorCode.SCALE_FAILED: "LAW 10",
    ErrorCode.SCALE_LIMIT_EXCEEDED: "LAW 10",
    ErrorCode.TICKET_NOT_FOUND: "LAW 12",
    ErrorCode.EXECUTION_UNKNOWN: "LAW 12",
}
