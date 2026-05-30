"""Phase G1 — Cognitive Orchestration: Runtime Models.  # LAW-1 # LAW-3 # LAW-8

Mirrors artifacts/design/g1/models/02_planning_and_feedback_models.py
and protocols/01_planner_protocols.py for runtime importability.

Shared types used by all G1 components.

Ref: Canon LAW 1-8, LAW 23-27, RULE 1-5
Ref: DEVELOPER.md §15.2, §15.9
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PlanStatus(str, Enum):  # LAW-3
    PENDING = "pending"
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    PUBLISHED = "published"
    ACTIVE = "active"
    ADAPTED = "adapted"
    COMPLETED = "completed"
    FAILED = "failed"
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


# ── ExecutionPlan ────────────────────────────────────────────────


@dataclass
class PlanNode:  # LAW-3
    node_id: str = ""
    tool_name: str = ""
    tool_params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    weight: float = 1.0


@dataclass
class ExecutionPlan:  # LAW-3 LAW-8
    plan_id: str
    version: int = 1
    plan_trace_id: str = ""
    intent: str = ""
    nodes: List[PlanNode] = field(default_factory=list)
    dag_topology: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    weight_hash: str = ""
    context_hash: str = ""
    status: PlanStatus = PlanStatus.PENDING
    created_at_ns: int = 0
    adapted_from: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def correlation_id(self) -> str:
        return f"plan:{self.plan_id}:v{self.version}"

    @property
    def is_adaptation(self) -> bool:
        return self.adapted_from is not None


# ── CriticAssessment ──────────────────────────────────────────────


@dataclass
class CriticAssessment:  # LAW-8
    assessor_id: str = ""
    plan_id: str = ""
    score: float = 0.0
    reason: str = ""
    detailed_feedback: List[str] = field(default_factory=list)

    @property
    def is_blocking(self) -> bool:
        return self.score is not None and self.score >= 0.8


# ── SwarmIntent ──────────────────────────────────────────────────


@dataclass
class SwarmIntent:  # LAW-23 LAW-24
    tool_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    priority: int = 0
    weight: float = 1.0


# ── Shared protocol types ────────────────────────────────────────


@dataclass
class DependencyEdge:  # LAW-3
    source: str
    target: str
    edge_type: str = "data"


@dataclass
class ToolMapping:  # LAW-23
    node_id: str
    tool_name: str
    required_capabilities: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0


@dataclass
class TopologyProfile:  # RULE-1
    node_count: int = 0
    edge_count: int = 0
    critical_path_length: int = 0
    parallel_branches: int = 0
    estimated_total_cost: float = 0.0


@dataclass
class CriticVerdict:  # LAW-8
    plan_id: str = ""
    assessments: List[Dict[str, Any]] = field(default_factory=list)
    overall_score: float = 0.0
    halt_recommended: bool = False
    escalate_recommended: bool = False


@dataclass
class SwarmNegotiation:  # LAW-23
    negotiation_id: str = ""
    requesting_agent: str = ""
    target_agent: str = ""
    proposed_tasks: List[str] = field(default_factory=list)
    status: NegotiationStatus = NegotiationStatus.PENDING
    counter_proposal: List[str] = field(default_factory=list)
