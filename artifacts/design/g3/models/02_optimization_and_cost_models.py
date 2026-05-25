"""Phase G3 — Optimizer Agent: Optimization & Cost Models.  # LAW-11 LAW-14 LAW-15 LAW-16

Formal dataclass and Enum definitions for the Optimizer Agent subsystem.

Models:
  OptimizationProposal   — Output of IOptimizerAgent.propose_optimization
  TopologyPatch          — DAG mutation descriptor
  CostBudget             — Hard/soft budget constraints for plan execution
  LoadDistributionReport — Per-worker resource snapshot

Ref: Canon LAW 11 (No Global State), LAW 14 (Resource Governance), LAW 15 (Cost Limits)
Ref: Canon LAW 16 (Fair Scheduling), RULE 1 (Determinism), RULE 3 (Feedback-Adaptation)
Ref: Canon RULE 5 (Recovery)
Ref: DEVELOPER.md §15.2, §15.9, §15.10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PatchOperation(str, Enum):  # LAW-14
    MERGE = "merge"
    SPLIT = "split"
    REORDER = "reorder"
    PRUNE = "prune"


class OptimizationSignal(str, Enum):  # LAW-8
    APPROVE = "approve"
    PROPOSE_PATCH = "propose_patch"
    REJECT = "reject"
    DEFER = "defer"


class BudgetScope(str, Enum):  # LAW-15
    PLAN = "plan"
    WORKER = "worker"
    GLOBAL = "global"


class OptimizationGuardReason(str, Enum):  # LAW-14 RULE-3
    """Reasons a Safe Patch Guard may reject a proposed optimisation."""
    INSUFFICIENT_COST_REDUCTION = "insufficient_cost_reduction"
    INSUFFICIENT_LATENCY_IMPROVEMENT = "insufficient_latency_improvement"
    MISSING_ROLLBACK_PLAN = "missing_rollback_plan"
    DAG_INTEGRITY_FAILED = "dag_integrity_failed"
    BUDGET_EXCEEDED = "budget_exceeded"


# ═══════════════════════════════════════════════════════════════════
# OptimizationProposal
# ═══════════════════════════════════════════════════════════════════


@dataclass
class OptimizationProposal:  # LAW-14 LAW-12
    """Structured output of IOptimizerAgent.propose_optimization.

    LAW 12: MUST carry optimizer_trace_id for cross-layer traceability.
    LAW 8: MUST include rollback_plan for recoverability.
    """
    plan_id: str = ""
    optimizer_trace_id: str = ""
    patch_type: PatchOperation = PatchOperation.REORDER
    affected_nodes: List[str] = field(default_factory=list)
    estimated_cost_delta: float = 0.0
    estimated_cost_delta_pct: float = 0.0
    latency_impact_ms: float = 0.0
    latency_impact_pct: float = 0.0
    confidence_score: float = 0.0
    rollback_plan: Optional[Dict[str, Any]] = None
    dag_integrity_check: bool = False
    rationale: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def meets_safe_patch_guards(self) -> bool:
        """Safe Patch Guards (RULE 3):
           - cost_reduction >= 5% OR latency_improvement >= 10%
           - rollback_plan != None
           - dag_integrity_check == True
        """
        cost_ok = self.estimated_cost_delta_pct <= -5.0
        latency_ok = self.latency_impact_pct <= -10.0
        return (cost_ok or latency_ok) and self.rollback_plan is not None and self.dag_integrity_check

    @property
    def is_cost_positive(self) -> bool:
        return self.estimated_cost_delta_pct <= -5.0


# ═══════════════════════════════════════════════════════════════════
# TopologyPatch
# ═══════════════════════════════════════════════════════════════════


@dataclass
class TopologyPatch:  # LAW-14
    """DAG mutation descriptor for IDAGTopologyOptimizer.

    Describes a single atomic change to the DAG topology.
    """
    operation: PatchOperation = PatchOperation.REORDER
    source_node: str = ""
    target_node: str = ""
    dependency_changes: List[Dict[str, str]] = field(default_factory=list)
    rationale: str = ""
    estimated_savings: float = 0.0


# ═══════════════════════════════════════════════════════════════════
# CostBudget
# ═══════════════════════════════════════════════════════════════════


@dataclass
class CostBudget:  # LAW-15
    """Hard and soft budget constraints for plan execution.

    LAW 15: All plans MUST respect both soft and hard limits.
    soft_limit — warning threshold; hard_limit — enforced maximum.
    """
    max_cpu_seconds: float = 0.0
    max_memory_mb: float = 0.0
    max_api_calls: int = 0
    soft_limit: float = 0.8
    hard_limit: float = 1.0
    scope: BudgetScope = BudgetScope.PLAN
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def soft_cpu(self) -> float:
        return self.max_cpu_seconds * self.soft_limit

    @property
    def soft_memory(self) -> float:
        return self.max_memory_mb * self.soft_limit

    @property
    def hard_cpu(self) -> float:
        return self.max_cpu_seconds * self.hard_limit

    @property
    def hard_memory(self) -> float:
        return self.max_memory_mb * self.hard_limit


# ═══════════════════════════════════════════════════════════════════
# LoadDistributionReport
# ═══════════════════════════════════════════════════════════════════


@dataclass
class LoadDistributionReport:  # LAW-16
    """Per-worker resource snapshot from IResourceBalancer.

    LAW 16: Worker load must be fairly distributed.
    """
    worker_id: str = ""
    assigned_nodes: List[str] = field(default_factory=list)
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    queue_depth: int = 0
    bottleneck_flag: bool = False
    timestamp_ns: int = 0


# ═══════════════════════════════════════════════════════════════════
# SafePatchGuardResult
# ═══════════════════════════════════════════════════════════════════


@dataclass
class SafePatchGuardResult:  # LAW-14 RULE-3
    """Result of evaluating all Safe Patch Guards.

    All preconditions MUST pass:
      1. cost_reduction >= 5% OR latency_improvement >= 10%
      2. rollback_plan != None
      3. dag_integrity_check == True
    """
    allowed: bool = False
    reason: str = ""
    failed_guard: Optional[OptimizationGuardReason] = None
    cost_reduction_pct: float = 0.0
    latency_improvement_pct: float = 0.0
    has_rollback_plan: bool = False
    dag_integrity_check: bool = False


# ═══════════════════════════════════════════════════════════════════
# OptimizerReport
# ═══════════════════════════════════════════════════════════════════


@dataclass
class OptimizerReport:  # LAW-12
    """Report produced by IOptimizerAgent.publish_report.

    LAW 12: Carries optimizer_trace_id for cross-layer tracing.
    """
    plan_id: str = ""
    optimizer_trace_id: str = ""
    signal: OptimizationSignal = OptimizationSignal.APPROVE
    proposals: List[OptimizationProposal] = field(default_factory=list)
    applied_patches: List[TopologyPatch] = field(default_factory=list)
    budget_status: Dict[str, Any] = field(default_factory=dict)
    load_reports: List[LoadDistributionReport] = field(default_factory=list)
    timestamp_ns: int = 0
