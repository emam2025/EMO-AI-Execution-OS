"""Phase G5 — Multi-Agent Runtime Models.  # LAW-11 LAW-12 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27

Shared types for all G5 components: AgentLifecycleManager, AgentContractEngine,
SwarmCoordinator, HierarchicalPlanner, and LifecycleStateMachine.

Ref: Canon LAW 11 (No Global State), LAW 12 (Traceability)
Ref: Canon LAW 23 (Service Ownership), LAW 24 (Dispatcher Ownership)
Ref: Canon LAW 25 (Message Boundaries), LAW 26 (Lifecycle Ownership)
Ref: Canon LAW 27 (One Service per Domain), RULE 1-5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentLifecycleState(str, Enum):
    IDLE = "idle"
    SPAWNING = "spawning"
    RUNNING = "running"
    PAUSED = "paused"
    DEGRADED = "degraded"
    TERMINATED = "terminated"


class ContractAgreementStatus(str, Enum):
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    SIGNED = "signed"
    BREACHED = "breached"
    VOIDED = "voided"


class TrustLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"


class BreachSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SubgoalStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentSpec:
    agent_id: str = ""
    capability_profile: List[str] = field(default_factory=list)
    resource_quota: Dict[str, float] = field(default_factory=lambda: {
        "max_cpu_sec": 60.0, "max_memory_mb": 256.0, "max_fds": 64,
    })
    lifecycle_policy: Dict[str, Any] = field(default_factory=lambda: {
        "max_runtime_sec": 3600, "auto_pause_idle_sec": 300,
        "heartbeat_interval_sec": 15, "checkpoint_interval_sec": 120,
    })
    trust_level: TrustLevel = TrustLevel.MEDIUM
    domain: str = ""
    mission_trace_id: str = ""


@dataclass
class AgentInstance:
    agent_id: str = ""
    spec: AgentSpec = field(default_factory=AgentSpec)
    state: AgentLifecycleState = AgentLifecycleState.IDLE
    health: HealthStatus = HealthStatus.HEALTHY
    last_heartbeat_ns: int = 0
    checkpoint_ref: str = ""
    assigned_domain: str = ""
    mission_trace_id: str = ""
    resource_usage: Dict[str, float] = field(default_factory=lambda: {
        "cpu_sec": 0.0, "memory_mb": 0.0, "fd_count": 0,
    })


@dataclass
class NegotiationPayload:
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
class Contract:
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
class BreachIncident:
    incident_id: str = ""
    contract_id: str = ""
    severity: BreachSeverity = BreachSeverity.LOW
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    detected_at_ns: int = 0
    recommended_action: str = "warn"
    mission_trace_id: str = ""


@dataclass
class SwarmContext:
    mission_id: str = ""
    mission_trace_id: str = ""
    parent_intent_id: str = ""
    assigned_agents: List[str] = field(default_factory=list)
    task_decomposition: Dict[str, Any] = field(default_factory=dict)
    consensus_threshold: float = 0.67
    timeout_sec: float = 300.0
    domain_boundaries: Dict[str, str] = field(default_factory=dict)


@dataclass
class ConsensusResult:
    consensus_reached: bool = False
    consensus_value: str = ""
    participation_rate: float = 0.0
    confidence: float = 0.0
    votes: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class Subgoal:
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
class CoherenceReport:
    coherent: bool = False
    score: float = 0.0
    gaps: List[str] = field(default_factory=list)
    hallucinations: List[str] = field(default_factory=list)
    mission_trace_id: str = ""
