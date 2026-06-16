"""G.2 — Critic & Adaptive Planning Models.

Pure frozen dataclasses and Enums for the Critic Agent and Adaptive Planner.
No business logic, no execution. stdlib only, zero internal imports.

Ref: DEVELOPER.md §16.2
Ref: Canon LAW 10, LAW 23
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class CriticDecision(Enum):
    """Decision outcome from plan review."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_ADAPTATION = "needs_adaptation"


@dataclass(frozen=True)
class CriticReport:
    """Immutable report from the Critic Agent after reviewing a Plan."""

    plan_id: str
    decision: CriticDecision
    reasons: List[str] = field(default_factory=list)
    suggested_adaptations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionFeedback:
    """Feedback from Runtime about a failed execution step."""

    plan_id: str
    failed_step_id: str
    error_type: str
    trace_summary: str = ""
