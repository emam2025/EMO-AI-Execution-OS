"""Phase G1 — Cognitive Orchestration: Formal Protocols.

Four typed protocols covering the full planning lifecycle:
  IPlannerAgent       — Plan synthesis, adaptation, validation, publication (LAW 3)
  IDAGSynthesizer     — Dependency resolution, tool mapping, priority assignment (RULE 1)
  ICriticFeedbackLoop — Quality evaluation, flaw detection, correction suggestion (LAW 8)
  ISwarmCoordinator   — Distributed task distribution, capability negotiation (LAW 23-27)

Ref: Canon LAW 1-8, LAW 23-27, RULE 1-5
Ref: DEVELOPER.md §15.2, §15.9, §15.13
Ref: ROADMAP Phase G1 — Cognitive Orchestration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol


# ════════════════════════════════════════════════════════════════════
# Shared dependency types (complements models/02_*)
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


class FlawType(str, Enum):  # LAW-8
    REDUNDANT_STEP = "redundant_step"
    MISSING_DEPENDENCY = "missing_dependency"
    SUBOPTIMAL_ORDERING = "suboptimal_ordering"
    CAPABILITY_MISMATCH = "capability_mismatch"
    RESOURCE_EXCEEDED = "resource_exceeded"
    DEADLOCK_DETECTED = "deadlock_detected"


class NegotiationStatus(str, Enum):  # LAW-23
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTERED = "countered"


# ════════════════════════════════════════════════════════════════════
# IPlannerAgent — Orchestrator of the planning lifecycle
# ════════════════════════════════════════════════════════════════════


class IPlannerAgent(Protocol):  # LAW-3 LAW-8
    """Orchestrates the full planning lifecycle.

    Consumes F1 Unified API for execution submission, F4 Observability
    for trace insight, and D9 Feedback Loop for adaptive refinement.

    Every plan carries a plan_trace_id for end-to-end traceability.
    """

    def synthesize_plan(
        self,
        intent: str,
        context: Dict[str, str],
        plan_trace_id: Optional[str] = None,
    ) -> str:
        """Accept a user/agent intent and produce an ExecutionPlan.

        Returns plan_id (UUID). The plan is stored internally in DRAFT
        status until validate_plan() is called.

        plan_trace_id, if provided, links this plan to an existing
        execution trace (e.g. from F4 Observability).
        """
        ...

    def adapt_plan(
        self,
        execution_id: str,
        feedback: Dict[str, Any],
        confidence_threshold: float = 0.8,
    ) -> str:
        """Adapt an active plan based on runtime feedback from D9.

        Returns new plan_id (new version). Original plan is archived.
        Adaptation is only permitted when:
          - feedback contains ≥ 2 critic signals OR
          - feedback.confidence ≥ confidence_threshold

        RULE 3: Guarded by adaptation guards — no random adaptation.
        """
        ...

    def validate_plan(
        self,
        plan_id: str,
    ) -> bool:
        """Validate a DRAFT plan for structural correctness.

        Checks: dependency completeness, no cycles, tool capability match,
        resource budget non-negative.  Returns True if valid.
        """
        ...

    def publish_plan(
        self,
        plan_id: str,
    ) -> str:
        """Publish an APPROVED plan to F1 Unified Runtime for execution.

        Returns execution_id from F1.submit().
        Published plans are immutable (RULE 2).
        """
        ...


# ════════════════════════════════════════════════════════════════════
# IDAGSynthesizer — DAG construction from intent
# ════════════════════════════════════════════════════════════════════


@dataclass
class DependencyEdge:  # LAW-3
    source: str
    target: str
    edge_type: str = "data"  # "data", "control", "resource"


@dataclass
class ToolMapping:  # LAW-23
    node_id: str
    tool_name: str
    required_capabilities: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0


@dataclass
class TopologyProfile:  # RULE-1
    node_count: int
    edge_count: int
    critical_path_length: int
    parallel_branches: int
    estimated_total_cost: float


class IDAGSynthesizer(Protocol):  # RULE-1
    """Resolves intent into a deterministic DAG structure.

    RULE 1: Same intent + context → same DAG topology every time.
    Uses D8 Service Mesh for tool registry lookups.
    """

    def resolve_dependencies(
        self,
        intent: str,
        context: Dict[str, str],
    ) -> List[DependencyEdge]:
        """Analyse intent and infer dependency edges between steps.

        Returns a list of DependencyEdge objects.  If intent is
        ambiguous, returns minimal safe set (most conservative).
        """
        ...

    def map_to_tools(
        self,
        nodes: List[str],
        context: Dict[str, str],
    ) -> Dict[str, ToolMapping]:
        """Map each DAG node to a registered tool via D8 Service Registry.

        Returns dict of node_id → ToolMapping.
        Unmappable nodes are flagged for escalation.
        """
        ...

    def assign_priorities(
        self,
        node_tool_map: Dict[str, ToolMapping],
        policy: Optional[Dict[str, float]] = None,
    ) -> Dict[str, int]:
        """Assign execution priority (1=highest) to each node.

        Priority based on: critical path position, resource demand,
        user-provided policy overrides.
        """
        ...

    def optimize_topology(
        self,
        edges: List[DependencyEdge],
        node_tool_map: Dict[str, ToolMapping],
    ) -> TopologyProfile:
        """Optimise DAG for parallelism and cost.

        Merges serial nodes where possible, identifies parallel
        branches, computes critical path.  Returns TopologyProfile.
        """
        ...


# ════════════════════════════════════════════════════════════════════
# ICriticFeedbackLoop — Quality evaluation & self-correction
# ════════════════════════════════════════════════════════════════════


@dataclass
class CriticVerdict:  # LAW-8
    plan_id: str
    assessments: List[Dict[str, Any]] = field(default_factory=list)
    overall_score: float = 0.0
    halt_recommended: bool = False
    escalate_recommended: bool = False


class ICriticFeedbackLoop(Protocol):  # LAW-8 RULE-3
    """Evaluates plan quality and recommends corrections.

    Receives runtime data from F4 Observability and D9 Feedback Loop
    to rate execution quality and detect flaw patterns.

    RULE 3: Corrections are bounded — no infinite adaptation loops.
    """

    def evaluate_plan_quality(
        self,
        plan_id: str,
        execution_metrics: Dict[str, float],
    ) -> CriticVerdict:
        """Score plan quality based on execution telemetry.

        Metrics include: success_rate, avg_duration, error_count,
        resource_efficiency.  Returns verdict with overall_score 0-1.
        """
        ...

    def detect_flaw_patterns(
        self,
        plan_id: str,
        timeline: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """Analyse execution timeline for recurring flaws.

        Returns list of flaw dicts with: flaw_type (FlawType),
        affected_node, severity, frequency.
        """
        ...

    def suggest_corrections(
        self,
        flaw_patterns: List[Dict[str, Any]],
        confidence_threshold: float = 0.7,
    ) -> List[Dict[str, str]]:
        """Propose corrections for detected flaws.

        Each correction includes: target_node, suggested_action,
        rationale, confidence_delta.
        Only returned if confidence ≥ confidence_threshold.
        """
        ...

    def rate_confidence(
        self,
        plan_id: str,
        execution_data: Dict[str, Any],
    ) -> float:
        """Rate confidence (0.0-1.0) in the current plan's success.

        Combines: historical success rate, critic verdict,
        feedback loop signals from D9.
        """
        ...


# ════════════════════════════════════════════════════════════════════
# ISwarmCoordinator — Multi-agent coordination
# ════════════════════════════════════════════════════════════════════


@dataclass
class SwarmNegotiation:  # LAW-23
    negotiation_id: str
    requesting_agent: str
    target_agent: str
    proposed_tasks: List[str] = field(default_factory=list)
    status: NegotiationStatus = NegotiationStatus.PENDING
    counter_proposal: List[str] = field(default_factory=list)


class ISwarmCoordinator(Protocol):  # LAW-23 LAW-24 LAW-27
    """Coordinates task distribution across a swarm of agents.

    Each agent owns exactly one capability domain (LAW 23).
    Tasks are routed via the D8 Service Mesh (LAW 24).
    No shared mutable state between agents (LAW 27).
    """

    def distribute_tasks(
        self,
        plan_id: str,
        node_assignments: Dict[str, str],
    ) -> Dict[str, List[str]]:
        """Distribute DAG nodes to agents by capability.

        Returns dict of agent_id → list of assigned node IDs.
        Distribution respects agent capability and current load.
        """
        ...

    def negotiate_capabilities(
        self,
        required_capability: str,
        requesting_agent: str,
        available_agents: List[str],
    ) -> SwarmNegotiation:
        """Negotiate transfer of a task requiring a specific capability.

        Returns SwarmNegotiation with status.
        If no agent can satisfy, status = REJECTED.
        """
        ...

    def resolve_conflicts(
        self,
        negotiations: List[SwarmNegotiation],
    ) -> List[SwarmNegotiation]:
        """Resolve all pending negotiations.

        Priority: CRITICAL tasks first, then by earliest deadline.
        Conflict resolution follows deterministic ordering (RULE 1).
        """
        ...

    def sync_state(
        self,
        agent_id: str,
        state_snapshot: Dict[str, Any],
    ) -> bool:
        """Synchronise agent state after task completion.

        Every agent publishes its state after each task (LAW 23-27).
        Returns True if sync was accepted.
        """
        ...
