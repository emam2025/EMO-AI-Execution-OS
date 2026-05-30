"""Phase G3 — Optimizer Agent: Runtime Models.  # LAW-11 LAW-14 LAW-15 LAW-16

Mirrors artifacts/design/g3/models/02_optimization_and_cost_models.py
for runtime importability.

Shared types used by all G3 components.

Ref: Canon LAW 11, LAW 14, LAW 15, LAW 16, RULE 1, RULE 3, RULE 5
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
    INSUFFICIENT_COST_REDUCTION = "insufficient_cost_reduction"
    INSUFFICIENT_LATENCY_IMPROVEMENT = "insufficient_latency_improvement"
    MISSING_ROLLBACK_PLAN = "missing_rollback_plan"
    DAG_INTEGRITY_FAILED = "dag_integrity_failed"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass
class OptimizationProposal:  # LAW-14 LAW-12
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
        cost_ok = self.estimated_cost_delta_pct <= -5.0
        latency_ok = self.latency_impact_pct <= -10.0
        return (cost_ok or latency_ok) and self.rollback_plan is not None and self.dag_integrity_check


@dataclass
class TopologyPatch:  # LAW-14
    operation: PatchOperation = PatchOperation.REORDER
    source_node: str = ""
    target_node: str = ""
    dependency_changes: List[Dict[str, str]] = field(default_factory=list)
    rationale: str = ""
    estimated_savings: float = 0.0


@dataclass
class CostBudget:  # LAW-15
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


@dataclass
class LoadDistributionReport:  # LAW-16
    worker_id: str = ""
    assigned_nodes: List[str] = field(default_factory=list)
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    queue_depth: int = 0
    bottleneck_flag: bool = False
    timestamp_ns: int = 0


@dataclass
class SafePatchGuardResult:  # LAW-14 RULE-3
    allowed: bool = False
    reason: str = ""
    failed_guard: Optional[OptimizationGuardReason] = None
    cost_reduction_pct: float = 0.0
    latency_improvement_pct: float = 0.0
    has_rollback_plan: bool = False
    dag_integrity_check: bool = False
