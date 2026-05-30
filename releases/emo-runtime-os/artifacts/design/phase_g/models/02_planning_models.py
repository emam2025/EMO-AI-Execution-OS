"""Phase G — Planning & Negotiation Data Models.

Core types for the Cognitive Orchestration Layer.  Every model carries
orchestration_trace_id for full audit (LAW 8) and tenant_id for isolation
(LAW 11 / LAW 15).

References:
  - ROADMAP 🔟 FINAL — Phase G: Cognitive Orchestration
  - DEVELOPER.md §15.14, §15.16
  - Canon LAW 1, 6, 8, 9, 11, 14, 15; RULE 1-3
  - artifacts/design/phase_g/protocols/01_cognitive_orchestration_protocols.py
  - artifacts/design/phase_l/models/02_memory_and_context_models.py

NON-NEGOTIABLE:
  - Every dataclass MUST carry orchestration_trace_id (LAW 8).
  - Every dataclass with tenant data MUST carry tenant_id (LAW 11).
  - Hashes are SHA-256, computed in __post_init__ where applicable.
  - No ExecutionCore, Engine, or Governance types appear in any model.
"""

from __future__ import annotations

import enum
import hashlib
import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════

class NegotiationRoundState(str, enum.Enum):
    """State of a single negotiation round between Planner and Critic."""
    PLANNER_SUBMITTED = "planner_submitted"
    CRITIC_REVIEWING = "critic_reviewing"
    CRITIC_APPROVED = "critic_approved"
    CRITIC_REJECTED = "critic_rejected"
    PLANNER_ADAPTING = "planner_adapting"
    RESOLVED = "resolved"


class DomainOwnership(str, enum.Enum):
    """Domain ownership boundary for agent responsibility."""
    PLANNER = "planner"
    CRITIC = "critic"
    OPTIMIZER = "optimizer"
    MEMORY_AGENT = "memory_agent"
    SHARED = "shared"


class ConflictType(str, enum.Enum):
    """Types of plan conflicts detected by the orchestration layer."""
    DAG_CYCLE = "dag_cycle"
    RESOURCE_OVERCOMMIT = "resource_overcommit"
    TENANT_SCOPE_MISMATCH = "tenant_scope_mismatch"
    INTENT_MISMATCH = "intent_mismatch"
    CRITIC_PLANNER_OSCILLATION = "critic_planner_oscillation"
    MEMORY_DEPENDENCY_MISSING = "memory_dependency_missing"


class OptimizationStrategy(str, enum.Enum):
    """Strategy used by the Optimizer to improve a DAG."""
    PARALLELIZE = "parallelize"
    REORDER = "reorder"
    BATCH = "batch"
    PRUNE_UNUSED = "prune_unused"
    CACHE_HIT = "cache_hit"


# ═══════════════════════════════════════════════════════════════
# Planning Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class NodeSpec:
    """A single node in a planned DAG."""
    node_id: str
    tool: str
    input_params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    estimated_cost_units: Decimal = Decimal("0")
    timeout_seconds: float = 30.0
    retry_count: int = 0
    memory_dependencies: List[str] = field(default_factory=list)


@dataclass
class PlanProposal:
    """A complete plan proposal from the PlannerAgent.

    LAW 1: Same (intent, context_window, constraints) → same hash.
    RULE 1: No ExecutionCore types — pure orchestration domain.
    """
    proposal_id: str
    intent: str
    dag_nodes: List[NodeSpec]
    execution_path_hash: str
    estimated_cost: Decimal = Decimal("0")
    memory_dependencies: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    tenant_id: str = ""
    orchestration_trace_id: str = ""
    created_at_ns: int = field(default_factory=lambda: time.time_ns())
    _hash: str = ""

    def __post_init__(self) -> None:
        node_ids = [n.node_id for n in self.dag_nodes]
        raw = json.dumps({
            "proposal_id": self.proposal_id,
            "intent": self.intent,
            "node_ids": node_ids,
            "execution_path_hash": self.execution_path_hash,
            "tenant_id": self.tenant_id,
        }, sort_keys=True, default=str)
        self._hash = hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class RevisedPlan:
    """A revised plan after adaptation on failure (PlannerAgent.adapt_on_failure).

    LAW 8: Full trace back to original proposal via orchestration_trace_id.
    """
    revised_proposal: PlanProposal
    original_proposal_id: str
    adaptation_reason: str
    retry_count: int = 0
    orchestration_trace_id: str = ""
    tenant_id: str = ""


# ═══════════════════════════════════════════════════════════════
# Critique Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class ViolationDetail:
    """A single violation found by the CriticAgent."""
    rule_ref: str
    severity: str  # "error" | "warning" | "info"
    description: str
    affected_node_id: Optional[str] = None
    suggested_fix: str = ""


@dataclass
class CritiqueReport:
    """Evaluation result from the CriticAgent.

    RULE 3: Critic MUST NOT accept cross-tenant plans without scope_verified.
    """
    proposal_id: str
    is_valid: bool
    violations: List[ViolationDetail] = field(default_factory=list)
    suggested_fixes: List[str] = field(default_factory=list)
    risk_level: str = "low"
    trace_id: str = ""
    orchestration_trace_id: str = ""
    tenant_id: str = ""
    evaluated_at_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class ValidationFailure:
    """Structured rejection from the CriticAgent.

    STOP-CONDITION: Must not be produced for cross-tenant violations
    without scope_verified=True (RULE 3).
    """
    proposal_id: str
    reason: str
    violation_code: str
    is_blocking: bool = True
    scope_verified: bool = False
    orchestration_trace_id: str = ""
    tenant_id: str = ""


# ═══════════════════════════════════════════════════════════════
# Negotiation Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class NegotiationCycle:
    """A single round of planner-critic negotiation.

    Guaranteed deterministic: same planner_submission + critic_feedback
    → same resolution_status (provided same constraints).
    """
    round_number: int
    planner_submission: PlanProposal
    critic_feedback: Optional[CritiqueReport] = None
    resolution_status: str = "pending"
    conflict_type: Optional[str] = None
    orchestration_trace_id: str = ""
    tenant_id: str = ""
    started_at_ns: int = field(default_factory=lambda: time.time_ns())
    resolved_at_ns: Optional[int] = None


# ═══════════════════════════════════════════════════════════════
# Optimization Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class OptimizedDAG:
    """Optimised DAG from the OptimizerAgent.

    LAW 14: Same (dag, resource_profile) → same OptimizedDAG deterministically.
    """
    original_proposal_id: str
    nodes: List[NodeSpec]
    edges: List[tuple[str, str]] = field(default_factory=list)
    estimated_cost: Decimal = Decimal("0")
    pareto_frontier: List[Dict[str, Any]] = field(default_factory=list)
    resource_delta: Dict[str, Decimal] = field(default_factory=dict)
    optimization_applied: Optional[OptimizationStrategy] = None
    orchestration_trace_id: str = ""
    tenant_id: str = ""


@dataclass
class ParallelHints:
    """Parallelism suggestions from the OptimizerAgent."""
    parallel_groups: List[List[str]] = field(default_factory=list)
    max_concurrency: int = 1
    optimal_batch_size: int = 1
    orchestration_trace_id: str = ""
    tenant_id: str = ""


# ═══════════════════════════════════════════════════════════════
# Observability Events
# ═══════════════════════════════════════════════════════════════

@dataclass
class PlanConflictReport:
    """Emitted when a plan conflict is detected (DAG cycle, oscillation, etc.)."""
    conflict_type: ConflictType
    proposal_id: str
    involved_agents: List[str]
    description: str
    orchestration_trace_id: str = ""
    tenant_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class CriticRejectionReport:
    """Emitted when the Critic rejects a plan proposal."""
    proposal_id: str
    violation_count: int
    risk_level: str
    is_blocking: bool
    orchestration_trace_id: str = ""
    tenant_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class OptimizationAppliedReport:
    """Emitted when an optimization strategy is applied."""
    proposal_id: str
    strategy: OptimizationStrategy
    cost_before: Decimal
    cost_after: Decimal
    orchestration_trace_id: str = ""
    tenant_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class TenantScopeViolationReport:
    """Emitted when a plan violates tenant scope boundaries."""
    proposal_id: str
    expected_tenant: str
    detected_tenant: str
    blocked: bool
    orchestration_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())
