"""D8.2 — Failure Propagation Model.

Defines the official failure propagation matrix as pure data contracts.
Enums and frozen Dataclasses only — no business logic, no execution.

Ref: DEVELOPER.md §15.15a D8.2
Ref: Canon LAW 20-22
"""

from dataclasses import dataclass
from enum import Enum


class FailureMode(Enum):
    """Defines how a service failure is handled."""

    RETRY = "retry"
    FALLBACK = "fallback"
    CIRCUIT_BREAK = "circuit_break"
    FAIL_FAST = "fail_fast"
    DEGRADE = "degrade"


class ConsistencyLevel(Enum):
    """Defines the consistency guarantee after failure handling."""

    STRONG = "strong"
    EVENTUAL = "eventual"
    NONE = "none"


@dataclass(frozen=True)
class FailureContext:
    """Immutable context describing a failure event between two services."""

    source_service: str
    target_service: str
    error_type: str
    timestamp: float


@dataclass(frozen=True)
class PropagationRule:
    """Immutable rule defining how a failure in one domain affects another.

    Example: "Dispatcher fails → Scheduler retries, LeaseManager releases"
    """

    source_domain: str
    effect_on: str
    action: str
    failure_mode: FailureMode
    consistency_level: ConsistencyLevel
