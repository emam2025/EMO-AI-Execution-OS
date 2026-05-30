"""Phase G1 — Cognitive Orchestration: Plan & Cognitive Feedback Models.

All dataclasses and enums for execution planning, DAG synthesis,
critic assessment, and swarm coordination.

Ref: Canon LAW 1-8, LAW 23-27, RULE 1-5
Ref: DEVELOPER.md §15.2, §15.9
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ════════════════════════════════════════════════════════════════════
# Shared Enums
# ════════════════════════════════════════════════════════════════════


class PlanStatus(str, Enum):  # LAW-3
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    ACTIVE = "active"
    ADAPTED = "adapted"
    COMPLETED = "completed"
    REJECTED = "rejected"
    HALTED = "halted"
    ESCALATED = "escalated"


class PlanningSignal(str, Enum):  # LAW-8
    OPTIMIZE = "optimize"
    ADAPT = "adapt"
    REJECT = "reject"
    HALT = "halt"
    ESCALATE = "escalate"


class FlawType(str, Enum):  # LAW-8
    REDUNDANT_STEP = "redundant_step"
    MISSING_DEPENDENCY = "missing_dependency"
    SUBOPTIMAL_ORDERING = "suboptimal_ordering"
    CAPABILITY_MISMATCH = "capability_mismatch"
    RESOURCE_EXCEEDED = "resource_exceeded"
    DEADLOCK_DETECTED = "deadlock_detected"


class StrategyProfile(str, Enum):  # LAW-1
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    RECOVERY = "recovery"


class NegotiationStatus(str, Enum):  # LAW-23
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTERED = "countered"


# ════════════════════════════════════════════════════════════════════
# ExecutionPlan — Core planning unit
# ════════════════════════════════════════════════════════════════════


@dataclass
class ExecutionPlan:  # LAW-3 LAW-8
    """A complete execution plan produced by the Planner Agent.

    Every plan MUST have:
      - plan_id      (UUID, unique)
      - version      (monotonic integer, incremented on adapt)
      - plan_trace_id (links to F4 Observability trace)

    Fields:
      intent              : original user/agent intent string
      dag_topology        : list of node definitions (dicts with id, deps, tool)
      estimated_cost      : total estimated execution cost
      confidence_score    : ICriticFeedbackLoop confidence rating (0.0-1.0)
      strategy_profile    : StrategyProfile enum
      status              : current PlanStatus
      created_at_ns       : monotonic creation timestamp
      adapted_from        : plan_id of the plan this was adapted from (None for original)
      metadata            : arbitrary key-value storage for context
    """

    plan_id: str
    version: int = 1
    plan_trace_id: str = ""
    intent: str = ""
    dag_topology: List[Dict[str, Any]] = field(default_factory=list)
    estimated_cost: float = 0.0
    confidence_score: float = 0.0
    strategy_profile: StrategyProfile = StrategyProfile.BALANCED
    status: PlanStatus = PlanStatus.DRAFT
    created_at_ns: int = 0
    adapted_from: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def correlation_id(self) -> str:
        """Cross-domain tracing key.

        Format: plan:{plan_id}:v{version}
        LAW 12: Every plan is traceable via correlation_id.
        """
        return f"plan:{self.plan_id}:v{self.version}"

    @property
    def is_adaptation(self) -> bool:
        return self.adapted_from is not None


# ════════════════════════════════════════════════════════════════════
# CriticAssessment — Quality evaluation unit from ICriticFeedbackLoop
# ════════════════════════════════════════════════════════════════════


@dataclass
class CriticAssessment:  # LAW-8
    """A single assessment from the Critic feedback loop.

    Fields:
      flaw_type       : type of flaw detected (FlawType)
      severity        : 0.0 (minor) – 1.0 (critical)
      suggested_fix   : human-readable description of the fix
      confidence_delta: change in confidence that this assessment causes
      affected_node   : DAG node ID affected (empty if plan-level)
      timestamp_ns    : when the assessment was made
    """

    flaw_type: FlawType = FlawType.SUBOPTIMAL_ORDERING
    severity: float = 0.0
    suggested_fix: str = ""
    confidence_delta: float = 0.0
    affected_node: str = ""
    timestamp_ns: int = 0

    @property
    def is_blocking(self) -> bool:
        return self.severity >= 0.8


# ════════════════════════════════════════════════════════════════════
# SwarmIntent — Agent capability advertisement & task assignment
# ════════════════════════════════════════════════════════════════════


@dataclass
class SwarmIntent:  # LAW-23 LAW-24
    """An agent's intent to participate in a swarm execution.

    Fields:
      agent_id          : unique agent identifier
      capability_set    : list of capabilities this agent provides
      assigned_tasks    : list of DAG node IDs assigned to this agent
      sync_state        : current state snapshot (load, health, last_task)
      negotiation_status: current NegotiationStatus
      load_score        : current utilisation 0.0-1.0 (for load-aware distribution)
    """

    agent_id: str = ""
    capability_set: List[str] = field(default_factory=list)
    assigned_tasks: List[str] = field(default_factory=list)
    sync_state: Dict[str, Any] = field(default_factory=dict)
    negotiation_status: NegotiationStatus = NegotiationStatus.PENDING
    load_score: float = 0.0
