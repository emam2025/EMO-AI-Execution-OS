"""Phase L — Cognitive Memory Data Models.

Mirrors artifacts/design/phase_l/models/02_memory_and_context_models.py.

LAW 6: Shared models defined outside runtime.
LAW 8: Every model carries cognitive_trace_id for auditability.
LAW 11: Tenant isolation — every tenant-aware model carries tenant_id.
LAW 14: Deterministic retrieval — SHA-256 hashes for reproducibility.
RULE 1: No cross-layer imports from ExecutionCore.
"""

from __future__ import annotations

import enum
import hashlib
import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


class MemoryLayer(str, enum.Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    SEMANTIC = "semantic"
    PROJECT = "project"


class PruningPolicy(str, enum.Enum):
    TTL_BASED = "ttl_based"
    FREQUENCY_BASED = "frequency_based"
    RELEVANCE_DECAY = "relevance_decay"


class RetrievalMode(str, enum.Enum):
    EXACT = "exact"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class PruneTrigger(str, enum.Enum):
    TTL_EXPIRY = "ttl_expiry"
    CAPACITY_REACHED = "capacity_reached"
    MANUAL = "manual"
    RELEVANCE_THRESHOLD = "relevance_threshold"


@dataclass
class SafetyBounds:
    tenant_id: str
    isolation_policy: str = "strict"
    cross_tenant_scope_verified: bool = False
    contains_execution_trace: bool = False
    contains_skill_data: bool = False
    contains_semantic_facts: bool = False
    _safety_hash: str = ""

    def __post_init__(self) -> None:
        raw = f"{self.tenant_id}:{self.isolation_policy}:{self.cross_tenant_scope_verified}"
        self._safety_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class TokenBudget:
    max_tokens: int = 4096
    reserved_for_trace: int = 2048
    reserved_for_skills: int = 1024
    reserved_for_graph: int = 512
    reserved_for_overhead: int = 512

    def __post_init__(self) -> None:
        assert self.max_tokens >= 1024, "TokenBudget must be >= 1024"
        have = (
            self.reserved_for_trace
            + self.reserved_for_skills
            + self.reserved_for_graph
            + self.reserved_for_overhead
        )
        assert have <= self.max_tokens, (
            f"TokenBudget reservations ({have}) exceed max ({self.max_tokens})"
        )

    @classmethod
    def scaled(cls, max_tokens: int) -> "TokenBudget":
        """Create a budget scaled proportionally to max_tokens."""
        ratio = max_tokens / 4096
        return cls(
            max_tokens=max_tokens,
            reserved_for_trace=max(256, int(2048 * ratio)),
            reserved_for_skills=max(128, int(1024 * ratio)),
            reserved_for_graph=max(64, int(512 * ratio)),
            reserved_for_overhead=max(64, int(512 * ratio)),
        )


@dataclass
class ContextWindow:
    trace_snippets: List[Dict[str, Any]] = field(default_factory=list)
    graph_context: Dict[str, Any] = field(default_factory=dict)
    skill_hints: List[Dict[str, Any]] = field(default_factory=list)
    safety_bounds: SafetyBounds | None = None
    token_budget: TokenBudget | None = None
    trace_id: str = ""
    tenant_id: str = ""
    cognitive_trace_id: str = ""
    _hash: str = ""

    def __post_init__(self) -> None:
        raw = json.dumps({
            "trace_snippets": self.trace_snippets,
            "graph_context": self.graph_context,
            "skill_hints": self.skill_hints,
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
        }, sort_keys=True, default=str)
        self._hash = hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class ContextOverflowReport:
    trace_id: str
    tenant_id: str
    requested_tokens: int
    actual_tokens: int
    budget: TokenBudget
    dropped_sections: List[str]
    cognitive_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class SkillNode:
    skill_id: str
    intent_pattern: str
    dag_template_hash: str
    tool_chain: List[Dict[str, Any]]
    success_rate: float = 0.0
    cost_profile: Dict[str, Decimal] = field(default_factory=dict)
    prerequisites: List[str] = field(default_factory=list)
    tenant_id: str = ""
    cognitive_trace_id: str = ""
    created_at_ns: int = field(default_factory=lambda: time.time_ns())
    _hash: str = ""

    def __post_init__(self) -> None:
        raw = json.dumps({
            "skill_id": self.skill_id,
            "intent_pattern": self.intent_pattern,
            "dag_template_hash": self.dag_template_hash,
            "tool_chain": self.tool_chain,
            "tenant_id": self.tenant_id,
        }, sort_keys=True, default=str)
        self._hash = hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class FailurePattern:
    pattern_id: str
    dag_id: str
    failure_hash: str
    failure_signal: str
    tool_chain_at_failure: List[Dict[str, Any]]
    tenant_id: str = ""
    cognitive_trace_id: str = ""
    created_at_ns: int = field(default_factory=lambda: time.time_ns())
    _hash: str = ""

    def __post_init__(self) -> None:
        raw = json.dumps({
            "pattern_id": self.pattern_id,
            "dag_id": self.dag_id,
            "failure_hash": self.failure_hash,
            "failure_signal": self.failure_signal,
            "tenant_id": self.tenant_id,
        }, sort_keys=True, default=str)
        self._hash = hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class SkillMismatchReport:
    query_intent: str
    retrieved_skill_id: str
    match_score: float
    threshold: float
    tenant_id: str
    cognitive_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class ForgettingPolicy:
    layer: MemoryLayer
    policy_type: PruningPolicy
    ttl_seconds: float | None = None
    max_entries: int = 10000
    relevance_decay_factor: float = 0.9
    tenant_id: str = ""
    cognitive_trace_id: str = ""
    _policy_hash: str = ""

    def __post_init__(self) -> None:
        assert 0 < self.relevance_decay_factor <= 1.0
        self._policy_hash = hashlib.sha256(
            json.dumps({
                "layer": self.layer.value,
                "policy_type": self.policy_type.value,
                "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_entries,
                "relevance_decay_factor": self.relevance_decay_factor,
                "tenant_id": self.tenant_id,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]


@dataclass
class PruneDecision:
    layer: MemoryLayer
    policy: ForgettingPolicy
    evicted_keys: List[str] = field(default_factory=list)
    surviving_count: int = 0
    trigger: PruneTrigger = PruneTrigger.CAPACITY_REACHED
    cognitive_trace_id: str = ""
    dry_run: bool = False
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class MemoryPruneTriggeredReport:
    layer: MemoryLayer
    evicted_count: int
    surviving_count: int
    policy_summary: str
    tenant_id: str
    cognitive_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class TenantIsolationEnforcedReport:
    operation: str
    tenant_id: str
    target_tenant_id: str
    blocked: bool
    cognitive_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class MemoryEntry:
    key: str
    layer: MemoryLayer
    payload: Dict[str, Any]
    tenant_id: str
    isolation_policy: str = "strict"
    cognitive_trace_id: str = ""
    stored_at_ns: int = field(default_factory=lambda: time.time_ns())
    last_access_ns: int = field(default_factory=lambda: time.time_ns())
    access_count: int = 0
    ttl_seconds: float | None = None
    relevance_score: float = 1.0
    _hash: str = ""

    def __post_init__(self) -> None:
        raw = json.dumps({
            "key": self.key,
            "layer": self.layer.value,
            "tenant_id": self.tenant_id,
            "cognitive_trace_id": self.cognitive_trace_id,
        }, sort_keys=True, default=str)
        self._hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
