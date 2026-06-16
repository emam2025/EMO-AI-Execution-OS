"""G.1 — Planner Agent Models.

Pure frozen dataclasses and Enums for the Planner Agent.
No business logic, no execution. stdlib only, zero internal imports.

Ref: DEVELOPER.md §16.1
Ref: Canon LAW 10, LAW 23
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class IntentType(Enum):
    """Classification of user intent."""

    CODE_GENERATION = "code_generation"
    DATA_ANALYSIS = "data_analysis"
    SYSTEM_REFACTOR = "system_refactor"
    UNKNOWN = "unknown"


class PlanStatus(Enum):
    """Lifecycle status of a Plan."""

    DRAFT = "draft"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    FAILED = "failed"


class StepStatus(Enum):
    """Status of an individual PlanStep."""

    PENDING = "pending"
    READY = "ready"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class Intent:
    """User intent to be translated into a Plan."""

    intent_id: str
    type: IntentType
    description: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanStep:
    """Single step in an execution plan (DAG node)."""

    step_id: str
    action: str
    tool_name: str
    dependencies: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING


@dataclass(frozen=True)
class Plan:
    """DAG plan generated from Intent. Immutable once validated."""

    plan_id: str
    intent_id: str
    steps: List[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT


@dataclass(frozen=True)
class PlanningContext:
    """Context provided to the Planner for decision-making."""

    available_tools: List[str] = field(default_factory=list)
    current_state: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlanningConstraint:
    """A single constraint applied during planning."""

    constraint_type: str
    value: str
    is_hard: bool = True
