"""Phase G5 — Multi-Agent Runtime: Protocols.  # LAW-11 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27

Formal typing.Protocol definitions for the Multi-Agent Runtime subsystem.
Each protocol maps to a specific ROADMAP Phase G5 responsibility:

  IAgentLifecycleManager   — Agent lifecycle (spawn, monitor, pause, terminate)
  IAgentContractEngine     — Negotiation protocols (capability negotiation, contract, breach)
  ISwarmCoordinator        — Swarm coordination (broadcast, conflict resolution, consensus, load)
  IHierarchicalPlanner     — Hierarchical planning (decompose, assign, merge, validate)

Ref: Canon LAW 11 (No Global State), LAW 23 (Service Ownership)
Ref: Canon LAW 24 (Dispatcher Ownership), LAW 25 (Message Boundaries)
Ref: Canon LAW 26 (Lifecycle Ownership), LAW 27 (One Service per Domain)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: DEVELOPER.md §15.2, §15.9, §15.15a
Ref: ROADMAP Phase G5
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════════
# Shared Enums (re-exported here for protocol self-containment)
# ═══════════════════════════════════════════════════════════════════


class AgentLifecycleState(str, Enum):  # LAW-26
    IDLE = "idle"
    SPAWNING = "spawning"
    RUNNING = "running"
    PAUSED = "paused"
    DEGRADED = "degraded"
    TERMINATED = "terminated"


class ContractAgreementStatus(str, Enum):  # LAW-24
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    SIGNED = "signed"
    BREACHED = "breached"
    VOIDED = "voided"


# ═══════════════════════════════════════════════════════════════════
# 1. IAgentLifecycleManager
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IAgentLifecycleManager(Protocol):  # LAW-26 LAW-27 RULE-4 RULE-5
    """Manages the full lifecycle of individual agents within the runtime.

    LAW 26: Each agent's lifecycle is owned by exactly one manager.
    LAW 27: Each agent belongs to exactly one domain — no cross-service
            lifecycle coupling.
    RULE 4: Agent isolation MUST be maintained across all lifecycle transitions.
    RULE 5: Terminated agents MUST be recoverable via checkpoint.

    Methods:
      spawn_agent:     Create and initialise an agent from an AgentSpec.
      monitor_health:  Return current health status of a running agent.
      pause_agent:     Suspend agent execution (preserve state).
      terminate_agent: Stop agent and release all resources.
    """

    def spawn_agent(
        self,
        spec: Dict[str, Any],
        mission_trace_id: str,
    ) -> Dict[str, Any]:
        """Spawn a new agent from an AgentSpec.

        Args:
            spec:             AgentSpec-compatible dict (see models).
            mission_trace_id: Cross-layer trace ID (LAW 12).

        Returns:
            Dict with:
              - agent_id (str):  Unique agent identifier.
              - spawn_status (str): "spawning" | "failed"
              - assigned_domain (str): Domain this agent belongs to (LAW 27).
              - checkpoint_ref (str): Initial checkpoint reference (RULE 5).
              - mission_trace_id (str): Echoed input trace ID.
        """

    def monitor_health(
        self,
        agent_id: str,
    ) -> Dict[str, Any]:
        """Return health status of a running agent.

        Returns:
            Dict with:
              - agent_id (str)
              - state (AgentLifecycleState): Current state.
              - health (str): "healthy" | "degraded" | "unreachable"
              - last_heartbeat_ns (int): Timestamp of last heartbeat.
              - resource_usage (Dict): {cpu_sec, memory_mb, fd_count}.
        """

    def pause_agent(
        self,
        agent_id: str,
    ) -> Dict[str, Any]:
        """Suspend agent execution while preserving internal state.

        LAW 26: Paused agents retain their domain ownership.
        RULE 5: Paused state MUST be checkpointed for recovery.

        Returns:
            Dict with:
              - agent_id (str)
              - state (str): Always "paused".
              - checkpoint_ref (str): Checkpoint reference for resume.
              - pause_timestamp_ns (int)
        """

    def terminate_agent(
        self,
        agent_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Terminate an agent and release all resources.

        LAW 26: Termination releases lifecycle ownership.
        LAW 27: All resources scoped to the agent's domain are freed.
        RULE 5: Final checkpoint is created before termination.

        Returns:
            Dict with:
              - agent_id (str)
              - state (str): Always "terminated".
              - final_checkpoint_ref (str)
              - resources_released (List[str])
              - mission_trace_id (str)
        """


# ═══════════════════════════════════════════════════════════════════
# 2. IAgentContractEngine
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IAgentContractEngine(Protocol):  # LAW-24 LAW-25 RULE-3
    """Manages capability negotiation and contract lifecycle between agents.

    LAW 24: Dispatcher owns the contract negotiation — no agent negotiates
            directly with another agent.
    LAW 25: All contract communication happens via message passing through
            the EventBus — no shared memory.
    RULE 3: Contract terms MUST be validated by safety guards before signing.

    Methods:
      negotiate_capabilities:  Match a capability request against an offer.
      validate_contract_terms: Validate terms against policy constraints.
      sign_agreement:          Finalise a contract between two parties.
      breach_detection:        Detect if an active contract has been breached.
    """

    def negotiate_capabilities(
        self,
        req: Dict[str, Any],
        offer: Dict[str, Any],
        mission_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Match a capability request against an offered capability set.

        Args:
            req:   NegotationPayload-compatible dict (request side).
            offer: NegotiationPayload-compatible dict (offer side).
            mission_trace_id: Cross-layer trace ID.

        Returns:
            Dict with:
              - match_score (float): [0,1] capability match score.
              - matched_capabilities (List[str]): Intersection of req/offer caps.
              - gaps (List[str]): Capabilities requested but not offered.
              - excess (List[str]): Capabilities offered but not requested.
              - mission_trace_id (str)
        """

    def validate_contract_terms(
        self,
        terms: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate contract terms against policy constraints.

        RULE 3: Guards enforce:
          - Term duration within policy limits.
          - Resource commitments within quota.
          - No capability escalation (offered caps ⊆ agent's profile).
          - SLA constraints are realistic.

        Returns:
            Dict with:
              - valid (bool): All terms pass validation.
              - violations (List[str]): Terms that failed validation.
              - confidence (float): Aggregate confidence [0,1].
        """

    def sign_agreement(
        self,
        contract: Dict[str, Any],
        signatures: Dict[str, str],
    ) -> Dict[str, Any]:
        """Sign a contract between two or more parties.

        LAW 24: Signatures are recorded by the Dispatcher on EventBus.
        LAW 25: The signed contract is emitted as an EventBus event.

        Returns:
            Dict with:
              - contract_id (str): Unique contract identifier.
              - status (str): "signed" | "rejected"
              - signed_at_ns (int)
              - mission_trace_id (str)
        """

    def breach_detection(
        self,
        contract_id: str,
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Detect if an active contract has been breached.

        Checks:
          - Capability usage exceeds declared scope.
          - Resource consumption violates quota.
          - SLA deadlines missed.
          - Communication pattern violates LAW 25 (direct reference).

        Returns:
            Dict with:
              - breached (bool): True if contract is breached.
              - severity (str): "low" | "medium" | "high" | "critical"
              - evidence (List[Dict]): Supporting evidence items.
              - recommended_action (str): "warn" | "renegotiate" | "terminate"
        """


# ═══════════════════════════════════════════════════════════════════
# 3. ISwarmCoordinator
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class ISwarmCoordinator(Protocol):  # LAW-11 LAW-23 LAW-25 RULE-1 RULE-2
    """Coordinates a swarm of agents executing a decomposed mission.

    LAW 11: No global state — all coordination state is scoped to the
            SwarmContext instance.
    LAW 23: Each swarm agent owns exactly one service domain.
    LAW 25: All inter-agent communication flows through EventBus messages;
            no direct references between agents.
    RULE 1: Conflict resolution is deterministic (same inputs → same outcome).
    RULE 2: No uncontrolled IO — swarm communication is always mediated.

    Methods:
      broadcast_task:     Distribute a task to all agents in the swarm.
      resolve_conflicts:  Deterministically resolve conflicting proposals.
      sync_consensus:     Reach consensus among swarm agents.
      distribute_load:    Rebalance work across agents.
    """

    def broadcast_task(
        self,
        swarm_ctx: Dict[str, Any],
        task: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Distribute a task to all agents in the swarm.

        LAW 25: Task is broadcast via EventBus messages, not direct calls.

        Args:
            swarm_ctx: SwarmContext-compatible dict.
            task:      Task specification with subgoal, inputs, constraints.

        Returns:
            Dict with:
              - broadcast_id (str): Unique broadcast event ID.
              - recipient_count (int): Number of agents that received.
              - ack_count (int): Agents that acknowledged receipt.
              - mission_trace_id (str)
        """

    def resolve_conflicts(
        self,
        swarm_ctx: Dict[str, Any],
        proposals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Deterministically resolve conflicting proposals from agents.

        RULE 1: Resolution follows a deterministic policy:
          1. Priority-based (higher trust_level wins).
          2. Tie-break by lexicographic agent_id.
          3. If still tied, earliest timestamp wins.

        Returns:
            Dict with:
              - resolution_id (str)
              - accepted_proposal (Dict): The winning proposal.
              - rejected_proposals (List[str]): agent_ids of rejected proposals.
              - rationale (str): Explanation of the resolution.
        """

    def sync_consensus(
        self,
        swarm_ctx: Dict[str, Any],
        votes: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Reach consensus among swarm agents on a decision.

        Args:
            swarm_ctx: SwarmContext with assigned_agents and consensus_threshold.
            votes:     Dict mapping agent_id -> {"vote": str, "confidence": float}.

        Returns:
            Dict with:
              - consensus_reached (bool): Threshold met.
              - consensus_value (str): The agreed value.
              - participation_rate (float): Fraction of agents that voted.
              - confidence (float): Aggregate confidence weighted by agent trust.
        """

    def distribute_load(
        self,
        swarm_ctx: Dict[str, Any],
        load_reports: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Rebalance work across swarm agents.

        LAW 23: Load is redistributed within service domain boundaries.
        LAW 27: No agent receives work from another agent's domain.

        Returns:
            Dict with:
              - reassignments (List[Dict]): [{task_id, from_agent, to_agent, reason}]
              - balance_score (float): [0,1] post-rebalance fairness.
              - domain_boundary_violations (List[str]): Any violations of LAW 27.
        """


# ═══════════════════════════════════════════════════════════════════
# 4. IHierarchicalPlanner
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IHierarchicalPlanner(Protocol):  # RULE-1 RULE-3 RULE-5
    """Decomposes high-level intents into hierarchical subgoals for the swarm.

    LAW 12: Every decomposition carries the parent mission_trace_id.
    RULE 1: Same intent → same decomposition (deterministic).
    RULE 3: Subgoal coherence is validated before assignment.
    RULE 5: Failed subgoals can be retried independently without replaying
            the full hierarchy.

    Methods:
      decompose_intent:   Recursively decompose an intent into subgoals.
      assign_subgoals:    Assign subgoals to specific agents in the swarm.
      merge_results:      Merge individual subgoal results into a coherent output.
      validate_coherence: Validate that subgoal results are consistent with parent intent.
    """

    def decompose_intent(
        self,
        parent: Dict[str, Any],
        mission_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Recursively decompose a parent intent into hierarchical subgoals.

        Args:
            parent: Intent dict with intent_id, goal, target_nodes, constraints.
            mission_trace_id: Cross-layer trace ID.

        Returns:
            Dict with:
              - decomposition_id (str): Unique ID for this decomposition.
              - subgoals (List[Dict]): [{subgoal_id, goal, dependencies, expected_output}]
              - dependency_graph (List[Dict]): [{from_subgoal, to_subgoal, type}]
              - mission_trace_id (str)
        """

    def assign_subgoals(
        self,
        subgoals: List[Dict[str, Any]],
        agents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Assign subgoals to specific agents based on capability match.

        LAW 27: Each subgoal is assigned to exactly one agent's domain.
        RULE 1: Assignment is deterministic — sorted by capability match
                score, then lexicographic agent_id.

        Returns:
            Dict with:
              - assignments (List[Dict]): [{subgoal_id, agent_id, rationale}]
              - unassigned (List[str]): Subgoals with no matching agent.
              - assignment_hash (str): SHA-256 of all assignments for determinism.
        """

    def merge_results(
        self,
        subgoal_results: List[Dict[str, Any]],
        dependency_graph: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge individual subgoal results into a coherent output.

        Walks the dependency graph bottom-up, merging results in order.
        RULE 5: If any subgoal failed, marks dependent subgoals as
                "cancelled" rather than executing them.

        Returns:
            Dict with:
              - merged_output (Dict): The final merged result.
              - subgoal_statuses (Dict[str, str]): Map of subgoal_id → status.
              - has_failures (bool): True if any subgoal failed.
        """

    def validate_coherence(
        self,
        parent_intent: Dict[str, Any],
        merged_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate that merged results are coherent with the parent intent.

        RULE 3: Coherence check verifies:
          - All target_nodes from intent are addressed.
          - No hallucinated capabilities appear in output.
          - Output schema matches expected structure.
          - Confidence threshold met (>= 0.7).

        Returns:
            Dict with:
              - coherent (bool): True if output matches intent.
              - score (float): Coherence score [0,1].
              - gaps (List[str]): Intent requirements not addressed.
              - hallucinations (List[str]): Output content not in intent.
        """
