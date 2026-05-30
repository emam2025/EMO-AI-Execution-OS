"""Phase G5 — Multi-Agent Runtime: Models.  # LAW-11 LAW-12 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27

Shared dataclass / Enum definitions for the Multi-Agent Runtime subsystem.
All models carry mission_trace_id (LAW 12) and lifecycle_policy (LAW 26)
for full traceability and ownership compliance.

Ref: Canon LAW 11 (No Global State), LAW 12 (Traceability)
Ref: Canon LAW 23 (Service Ownership), LAW 24 (Dispatcher Ownership)
Ref: Canon LAW 25 (Message Boundaries), LAW 26 (Lifecycle Ownership)
Ref: Canon LAW 27 (One Service per Domain), RULE 1-5
Ref: DEVELOPER.md §15.2, §15.9, §15.15a
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════
# Enums
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


class TrustLevel(str, Enum):  # RULE-1
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HealthStatus(str, Enum):  # LAW-26
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"


class BreachSeverity(str, Enum):  # RULE-3
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SubgoalStatus(str, Enum):  # RULE-5
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ═══════════════════════════════════════════════════════════════════
# Agent-level models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class AgentSpec:  # LAW-26 LAW-27
    """Specification for spawning an agent.

    agent_id:         Unique identifier across the runtime.
    capability_profile:  Declared capabilities (functions, tools, domains).
    resource_quota:   Max CPU, memory, and fd count.
    lifecycle_policy:  Policy dict (max runtime, auto-pause, heartbeat interval).
    trust_level:       Assigned trust level for conflict resolution priority.
    domain:            Service domain this agent belongs to (LAW 27).
    mission_trace_id:  LAW 12 trace ID for this agent's mission.
    """
    agent_id: str = ""
    capability_profile: List[str] = field(default_factory=list)
    resource_quota: Dict[str, float] = field(default_factory=lambda: {
        "max_cpu_sec": 60.0,
        "max_memory_mb": 256.0,
        "max_fds": 64,
    })
    lifecycle_policy: Dict[str, Any] = field(default_factory=lambda: {
        "max_runtime_sec": 3600,
        "auto_pause_idle_sec": 300,
        "heartbeat_interval_sec": 15,
        "checkpoint_interval_sec": 120,
    })
    trust_level: TrustLevel = TrustLevel.MEDIUM
    domain: str = ""
    mission_trace_id: str = ""


@dataclass
class AgentInstance:  # LAW-26 LAW-27
    """Runtime instance of a spawned agent.

    Mirrors the live state managed by IAgentLifecycleManager.
    """
    agent_id: str = ""
    spec: AgentSpec = field(default_factory=AgentSpec)
    state: AgentLifecycleState = AgentLifecycleState.IDLE
    health: HealthStatus = HealthStatus.HEALTHY
    last_heartbeat_ns: int = 0
    checkpoint_ref: str = ""
    assigned_domain: str = ""
    mission_trace_id: str = ""
    resource_usage: Dict[str, float] = field(default_factory=lambda: {
        "cpu_sec": 0.0,
        "memory_mb": 0.0,
        "fd_count": 0,
    })


@dataclass
class NegotiationPayload:  # LAW-24 LAW-25
    """Payload for capability negotiation between agents.

    All negotiation flows through the Dispatcher (LAW 24) via
    EventBus messages (LAW 25) — no direct agent-to-agent calls.
    """
    offer_id: str = ""
    requester_agent_id: str = ""
    responder_agent_id: str = ""
    requested_caps: List[str] = field(default_factory=list)
    offered_caps: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    agreement_status: ContractAgreementStatus = ContractAgreementStatus.PENDING
    mission_trace_id: str = ""
    signed_at_ns: int = 0


@dataclass
class Contract:  # LAW-24 LAW-25
    """A signed contract between two or more agents.

    Immutable after signing. Breach detection creates a new
    incident rather than modifying the contract.
    """
    contract_id: str = ""
    parties: List[str] = field(default_factory=list)
    terms: Dict[str, Any] = field(default_factory=dict)
    signed_caps: List[str] = field(default_factory=list)
    status: ContractAgreementStatus = ContractAgreementStatus.PENDING
    signed_at_ns: int = 0
    expires_at_ns: int = 0
    mission_trace_id: str = ""
    dispatcher_signature: str = ""


@dataclass
class BreachIncident:  # RULE-3
    """Record of a contract breach detection event."""
    incident_id: str = ""
    contract_id: str = ""
    severity: BreachSeverity = BreachSeverity.LOW
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    detected_at_ns: int = 0
    recommended_action: str = "warn"
    mission_trace_id: str = ""


# ═══════════════════════════════════════════════════════════════════
# Swarm-level models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class SwarmContext:  # LAW-11 LAW-23 LAW-25
    """Mutable coordination context for a single swarm mission.

    LAW 11: Context is scoped to this instance — no global swarm state.
    LAW 23: All assigned_agents own exactly one service domain.
    LAW 25: Agent communication is mediated via EventBus, not direct refs.
    """
    mission_id: str = ""
    mission_trace_id: str = ""
    parent_intent_id: str = ""
    assigned_agents: List[str] = field(default_factory=list)
    task_decomposition: Dict[str, Any] = field(default_factory=dict)
    consensus_threshold: float = 0.67
    timeout_sec: float = 300.0
    conflict_resolution_policy: str = "deterministic_priority"
    domain_boundaries: Dict[str, str] = field(default_factory=dict)


@dataclass
class SwarmTask:  # RULE-1 RULE-5
    """A task distributed to swarm agents via broadcast."""
    task_id: str = ""
    subgoal_id: str = ""
    agent_id: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    deadline_ns: int = 0
    status: SubgoalStatus = SubgoalStatus.PENDING
    mission_trace_id: str = ""


@dataclass
class ConsensusResult:  # RULE-1
    """Result of a swarm consensus round."""
    consensus_reached: bool = False
    consensus_value: str = ""
    participation_rate: float = 0.0
    confidence: float = 0.0
    votes: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# Planning-level models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Subgoal:  # RULE-1 RULE-5
    """A single subgoal in the hierarchical decomposition."""
    subgoal_id: str = ""
    parent_intent_id: str = ""
    goal: str = ""
    dependencies: List[str] = field(default_factory=list)
    expected_output: Dict[str, Any] = field(default_factory=dict)
    assigned_agent: str = ""
    status: SubgoalStatus = SubgoalStatus.PENDING
    confidence: float = 0.0
    mission_trace_id: str = ""


@dataclass
class DecompositionResult:  # RULE-1
    """Result of decomposing a parent intent."""
    decomposition_id: str = ""
    parent_intent_id: str = ""
    subgoals: List[Subgoal] = field(default_factory=list)
    dependency_graph: List[Dict[str, Any]] = field(default_factory=list)
    mission_trace_id: str = ""


@dataclass
class CoherenceReport:  # RULE-3
    """Validation report for merged subgoal coherence."""
    coherent: bool = False
    score: float = 0.0
    gaps: List[str] = field(default_factory=list)
    hallucinations: List[str] = field(default_factory=list)
    mission_trace_id: str = ""
