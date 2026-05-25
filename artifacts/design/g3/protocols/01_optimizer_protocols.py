"""Phase G3 — Optimizer Agent: Protocols.  # LAW-11 LAW-14 LAW-15 LAW-16

Formal typing.Protocol definitions for the Optimizer Agent subsystem.
Each protocol maps to a specific ROADMAP Phase G3 responsibility:

  IOptimizerAgent        — Top-level orchestrator (evaluate → propose → apply → publish)
  IDAGTopologyOptimizer  — DAG structure analysis, redundancy detection, dependency rebalance
  ICostOptimizer         — Execution cost estimation, waste detection, budget enforcement
  IResourceBalancer      — Load distribution, hotspot detection, worker reassignment

Ref: Canon LAW 11 (No Global State), LAW 14 (Resource Governance), LAW 15 (Cost Limits)
Ref: Canon LAW 16 (Fair Scheduling), RULE 1 (Determinism), RULE 3 (Feedback-Adaptation)
Ref: Canon RULE 5 (Recovery)
Ref: DEVELOPER.md §15.2, §15.9, §15.10, §15.13
Ref: ROADMAP Phase G3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ── Re-usable value types (shared across protocols) ──────────────


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


# ═══════════════════════════════════════════════════════════════════
# 1. IOptimizerAgent
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IOptimizerAgent(Protocol):  # LAW-14 LAW-15 LAW-16
    """Top-level orchestrator of the Optimizer Agent subsystem.

    Consumes G1 plans, G2 critic assessments, F4 traces, and F3 metrics:
      - evaluate_plan: score plan quality against cost/latency/load metrics
      - propose_optimization: generate topology patches
      - apply_topology_patch: apply a validated patch to the DAG
      - publish_report: emit optimisation report to EventBus

    LAW 12: Every optimisation carries an optimizer_trace_id.
    RULE 1: All proposals are deterministic given same inputs.
    """

    def evaluate_plan(
        self,
        plan_id: str,
        plan: Dict[str, Any],
        metrics: Dict[str, Any],
        optimizer_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Evaluate a plan against cost/latency/load metrics.

        Args:
            plan_id:    The G1 ExecutionPlan.plan_id.
            plan:       Dict with nodes, dag_topology, estimated_cost.
            metrics:    Dict with cpu_seconds, memory_mb, api_calls,
                        latency_p95, worker_load.
            optimizer_trace_id:  Cross-layer trace ID.

        Returns:
            Dict with evaluation_score, cost_efficiency, load_balance_score,
            latency_risk, violations[].
        """

    def propose_optimization(
        self,
        plan_id: str,
        evaluation: Dict[str, Any],
        cost_budget: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Produce optimisation proposals from an evaluation.

        Args:
            plan_id:     The plan under evaluation.
            evaluation:  The evaluation result dict from evaluate_plan.
            cost_budget: CostBudget-compatible dict.

        Returns:
            List of OptimizationProposal-compatible dicts, each carrying
            optimizer_trace_id, patch_type, affected_nodes, estimated_cost_delta.
        """

    def apply_topology_patch(
        self,
        plan_id: str,
        patch: Dict[str, Any],
        dag: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply a validated topology patch to the DAG.

        Safe Patch Guards must pass before application (see §2).

        Returns:
            Dict with updated_dag, patch_applied (bool), integrity_check (bool).
        """

    def publish_report(
        self,
        plan_id: str,
        report: Dict[str, Any],
    ) -> None:
        """Publish optimisation report to EventBus.

        §15.13: All reports MUST be routed to EventBus topics:
          - optimizer.plan.evaluated
          - optimizer.patch.proposed
          - optimizer.patch.applied
          - optimizer.budget.exceeded
        """


# ═══════════════════════════════════════════════════════════════════
# 2. IDAGTopologyOptimizer
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IDAGTopologyOptimizer(Protocol):  # LAW-14 RULE-1
    """DAG topology optimisation subsystem.

    Analyses DAG structure for redundancy, parallelism, and dependency
    efficiency. All methods are deterministic (RULE 1).

    LAW 14: Topology changes MUST preserve DAG integrity.
    """

    def detect_redundant_nodes(
        self,
        nodes: List[Dict[str, Any]],
        dag: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Detect redundant or dead nodes in the DAG.

        Returns:  List of {node_id, reason, estimated_waste}.
        """

    def merge_parallel_paths(
        self,
        nodes: List[Dict[str, Any]],
        dag: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Detect parallel paths that can be merged.

        Returns:  List of {source_node, target_node, merge_strategy, cost_savings}.
        """

    def rebalance_dependencies(
        self,
        nodes: List[Dict[str, Any]],
        dag: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Rebalance dependency edges for optimal parallelism.

        Returns:  List of {node_id, current_deps[], suggested_deps[], rationale}.
        """

    def validate_dag_integrity(
        self,
        nodes: List[Dict[str, Any]],
        dag: List[Dict[str, Any]],
    ) -> bool:
        """Validate DAG integrity after modifications.

        Checks:
          - All node references in edges exist
          - No cycles
          - Single entry/exit (or documented multi-entry)
          - No orphan nodes

        Returns:  True if DAG is valid.
        """


# ═══════════════════════════════════════════════════════════════════
# 3. ICostOptimizer
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class ICostOptimizer(Protocol):  # LAW-15 RULE-3
    """Execution cost optimisation subsystem.

    Estimates cost, detects waste, suggests alternatives, and enforces
    budgets. All cost functions are deterministic (RULE 1).

    LAW 15: All plans MUST respect cost budgets.
    """

    def estimate_execution_cost(
        self,
        nodes: List[Dict[str, Any]],
        baseline_costs: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Estimate total execution cost of a DAG.

        Returns:  Dict with total_cpu_seconds, total_memory_mb,
                  total_api_calls, estimated_duration_ms.
        """

    def detect_resource_waste(
        self,
        nodes: List[Dict[str, Any]],
        execution_trace: List[Dict[str, Any]],
        thresholds: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """Detect resource waste from execution traces.

        Returns:  List of {node_id, wasted_cpu, wasted_memory, reason}.
        """

    def suggest_alternative_tools(
        self,
        node: Dict[str, Any],
        tool_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Suggest cheaper/faster tool alternatives for a node.

        Returns:  List of {tool_name, estimated_cost, estimated_latency, trade_offs}.
        """

    def enforce_budget(
        self,
        estimated_cost: Dict[str, Any],
        budget: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Enforce cost budget against estimated cost.

        Returns:  Dict with within_budget (bool), exceeded_fields[],
                  overage_percent, recommended_actions[].
        """


# ═══════════════════════════════════════════════════════════════════
# 4. IResourceBalancer
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IResourceBalancer(Protocol):  # LAW-16 RULE-5
    """Resource balancing subsystem.

    Computes load distribution, detects hotspots, suggests worker
    reassignment, and validates fairness constraints.

    LAW 16: Worker assignment MUST be fair across the cluster.
    RULE 5: Reassignment MUST be recoverable.
    """

    def compute_load_distribution(
        self,
        worker_snapshots: List[Dict[str, Any]],
        node_assignments: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Compute load distribution across workers.

        Returns:  List of LoadDistributionReport-compatible dicts with
                  worker_id, assigned_nodes, cpu_utilization, memory_utilization,
                  queue_depth, bottleneck_flag.
        """

    def detect_hotspots(
        self,
        load_reports: List[Dict[str, Any]],
        thresholds: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """Detect resource hotspots from load reports.

        Returns:  List of {worker_id, overloaded_resource, current_load,
                  recommended_action}.
        """

    def suggest_worker_reassignment(
        self,
        hotspot: Dict[str, Any],
        available_workers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Suggest reassignment actions for a hotspot.

        Returns:  List of {node_id, from_worker, to_worker, estimated_improvement}.
        """

    def validate_fairness(
        self,
        load_reports: List[Dict[str, Any]],
        fairness_threshold: float = 0.2,
    ) -> Dict[str, Any]:
        """Validate fairness of load distribution.

        LAW 16: Worker load must be within fairness_threshold of mean.

        Returns:  Dict with fair (bool), max_imbalance, variance,
                  violated_workers[].
        """
