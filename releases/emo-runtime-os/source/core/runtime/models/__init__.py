"""F1 — Runtime Models.

Exports the error taxonomy and response envelope.
"""

from core.runtime.models.api_errors import (
    APIError,
    ErrorCategory,
    ErrorCode,
    ErrorSeverity,
    SubmissionRejected,
    CheckpointMissing,
    InvalidStateTransition,
    LeaseConflict,
    QuotaExceeded,
    WorkerUnavailable,
    ExecutionTimeout,
    ReplayMismatch,
    RollbackFailed,
    ScaleError,
    ScaleLimitExceeded,
    WorkerRegistrationFailed,
    TicketNotFound,
    ResponseEnvelope,
    ERROR_CODE_LAW_MAP,
)

__all__ = [
    "APIError",
    "ErrorCategory",
    "ErrorCode",
    "ErrorSeverity",
    "SubmissionRejected",
    "CheckpointMissing",
    "InvalidStateTransition",
    "LeaseConflict",
    "QuotaExceeded",
    "WorkerUnavailable",
    "ExecutionTimeout",
    "ReplayMismatch",
    "RollbackFailed",
    "ScaleError",
    "ScaleLimitExceeded",
    "WorkerRegistrationFailed",
    "TicketNotFound",
    "ResponseEnvelope",
    "ERROR_CODE_LAW_MAP",
]
