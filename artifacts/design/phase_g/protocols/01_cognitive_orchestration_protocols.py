"""Phase G — Cognitive Orchestration Protocols.

Defines the three agent protocols for the Cognitive Orchestration Layer.
Each protocol is a @runtime_checkable typing.Protocol.

References:
  - ROADMAP 🔟 FINAL — Phase G: Cognitive Orchestration
  - DEVELOPER.md §15.14, §15.16
  - Canon LAW 1 (Determinism), LAW 9 (Governance Independence), RULE 1 (No cross-layer)
  - artifacts/validation/memory/MEMORY_OPERATIONAL_CERTIFICATE.json
  - artifacts/design/phase_l/protocols/01_cognitive_memory_protocols.py

NON-NEGOTIABLE:
  - Every method accepts cognitive_trace_id (LAW 8, backward traceability).
  - Every method expecting tenant data carries tenant_id (LAW 11, LAW 15).
  - All plans are deterministic: same (intent + context + constraints) → same PlanProposal.
  - No protocol method imports or references ExecutionCore, Engine, or Governance types.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════
# Domain Type Forward References (defined in models/)
# ═══════════════════════════════════════════════════════════════

# PlanProposal, CritiqueReport, OptimizedDAG, ParallelHints are defined
# in artifacts/design/phase_g/models/02_planning_models.py and referenced
# here as return types.  They are imported at usage sites, not here.


# ═══════════════════════════════════════════════════════════════
# IPlannerAgent
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class IPlannerAgent(Protocol):
    """Agent responsible for synthesizing DAG plans from intent + memory.

    LAW 1: Same (intent, context_window) → same PlanProposal (deterministic).
    LAW 9: Planner operates independently of governance — no policy injection.
    RULE 1: No direct access to ExecutionCore or Engine internals.
    """

    async def synthesize_dag(
        self,
        intent: str,
        context_window: Dict[str, Any],
        tenant_id: str,
        constraints: Optional[Dict[str, Any]] = None,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Synthesize a DAG proposal from natural language intent and context.

        Args:
            intent: Natural-language or structured intent string.
            context_window: Compiled ContextWindow from IContextCompiler (Phase L).
            tenant_id: Tenant scope (LAW 11).
            constraints: Optional runtime constraints (budget, timeout, priority).
            cognitive_trace_id: Trace ID for LAW 8 audit.

        Returns:
            PlanProposal (serialised as dict with keys:
                dag_nodes, execution_path_hash, estimated_cost,
                memory_dependencies, confidence_score, cognitive_trace_id).
        """

    async def adapt_on_failure(
        self,
        feedback: Dict[str, Any],
        original_proposal: Dict[str, Any],
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Revise a plan based on execution feedback or critic rejection.

        LAW 1: Same (original_proposal, feedback) → same RevisedPlan.
        Guard G-P1: Adapt cycle counter must not exceed MAX_RETRY.
        """


# ═══════════════════════════════════════════════════════════════
# ICriticAgent
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class ICriticAgent(Protocol):
    """Agent responsible for evaluating plan proposals against constraints.

    RULE 3: Critic must NEVER accept a plan without scope_verified when
    cross-tenant context is present. See G-M3 in MemoryStateMachine.
    """

    async def evaluate_plan(
        self,
        proposal: Dict[str, Any],
        constraints: Dict[str, Any],
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Evaluate a PlanProposal against governance and safety constraints.

        Returns:
            CritiqueReport (serialised as dict with keys:
                is_valid, violations[], suggested_fixes[], risk_level,
                trace_id, cognitive_trace_id).
        """

    async def reject_with_reason(
        self,
        proposal: Dict[str, Any],
        violation: str,
        tenant_id: str,
        scope_verified: bool = False,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Produce a structured ValidationFailure for a rejected proposal.

        STOP-CONDITION: Must refuse to call this if scope_verified is False
        and the violation involves cross-tenant context (RULE 3).
        """


# ═══════════════════════════════════════════════════════════════
# IOptimizerAgent
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class IOptimizerAgent(Protocol):
    """Agent responsible for optimising an approved DAG for execution.

    LAW 14: Same (dag, resource_profile) → same OptimizedDAG (deterministic).
    RULE 1: No cross-layer imports — operates on DAG shape only.
    """

    async def optimize_execution_graph(
        self,
        dag: Dict[str, Any],
        resource_profile: Dict[str, Any],
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Optimise an approved DAG given resource constraints.

        Returns:
            OptimizedDAG (serialised dict with keys:
                nodes[], edges[], estimated_cost, pareto_frontier[],
                resource_delta, cognitive_trace_id).
        """

    async def suggest_parallelism(
        self,
        dag: Dict[str, Any],
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Suggest parallelism hints for the execution scheduler.

        Returns:
            ParallelHints (serialised dict with keys:
                parallel_groups[], max_concurrency, optimal_batch_size,
                cognitive_trace_id).
        """


# ═══════════════════════════════════════════════════════════════
# Lifecycle Enums
# ═══════════════════════════════════════════════════════════════

class OrchestrationEventType(str, enum.Enum):
    """Events emitted by the orchestration layer to EventBus."""
    PLAN_PROPOSED = "plan_proposed"
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"
    OPTIMIZATION_APPLIED = "optimization_applied"
    FEEDBACK_LOOP_TRIGGERED = "feedback_loop_triggered"
    TENANT_SCOPE_VIOLATION = "tenant_scope_violation"
    ORCHESTRATION_ABORTED = "orchestration_aborted"
    PLAN_CONFLICT_DETECTED = "plan_conflict_detected"


class RiskLevel(str, enum.Enum):
    """Risk level assigned by CriticAgent."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResolutionStatus(str, enum.Enum):
    """Resolution status of a NegotiationCycle."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ABORTED = "aborted"
    STALLED = "stalled"


class OrchestrationState(str, enum.Enum):
    """State of the orchestration lifecycle (mirrors 03_orchestration_lifecycle.md)."""
    PLANNING = "planning"
    CRITICIZING = "criticizing"
    OPTIMIZING = "optimizing"
    APPROVED = "approved"
    REJECTED = "rejected"
    ABORTED = "aborted"
    EXECUTING = "executing"
    COMPLETED = "completed"
