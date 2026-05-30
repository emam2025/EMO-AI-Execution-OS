"""Phase L — Cognitive Memory & Context Data Models.

Design overview:
  Defines the shared data types for the Phase L Cognitive Memory Layer.
  Every model carries cognitive_trace_id for full audit (LAW 8) and
  tenant_id for isolation enforcement (LAW 11 / LAW 15).

  The models are split into four groups:
    1. Memory Enums     — layer types, pruning policies, retrieval modes
    2. Context Models   — ContextWindow, SafetyBounds, TokenBudget
    3. Skill Models     — SkillNode, FailurePattern
    4. Forgetting Models — ForgettingPolicy, PruneDecision

References:
  - ROADMAP 🔟 FINAL — Phase L: Cognitive Memory OS
  - DEVELOPER.md §15.14, §15.16
  - Canon LAW 6 (Shared models outside runtime)
  - Canon LAW 8 (Recoverability)
  - Canon LAW 11 (Enterprise Isolation)
  - Canon LAW 14 (Deterministic Retrieval)
  - Canon LAW 15 (Tenant Context Isolation)
  - RULE 1 (No cross-layer imports)
  - RULE 2 (All systems require interfaces)
  - artifacts/design/phase_l/protocols/01_cognitive_memory_protocols.py

NON-NEGOTIABLE:
  - Every dataclass MUST carry cognitive_trace_id (LAW 8).
  - Every dataclass with tenant data MUST carry tenant_id + isolation_policy (LAW 11).
  - Hashes are SHA-256, computed in __post_init__ where applicable.
  - No runtime-internal types (ExecutionEvent, DAG, Engine) appear in any model.
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
# Group 1: Memory Enums
# ═══════════════════════════════════════════════════════════════

class MemoryLayer(str, enum.Enum):
    """The four layers of the Cognitive Memory hierarchy.

    DESIGN RATIONALE:
      WORKING     — Volatile, session-scoped.  Lost on session end.
      EPISODIC    — Trace-backed.  Durable, indexed by execution_trace_id.
      PROCEDURAL  — Skill / plans / failure patterns.  Governed by SkillGraph.
      SEMANTIC    — Graph facts, static knowledge.  Rarely pruned.
    """
    WORKING = "working"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    SEMANTIC = "semantic"


class PruningPolicy(str, enum.Enum):
    """Deterministic forgetting strategies.

    DESIGN RATIONALE:
      TTL_BASED         — Simple time-based expiry.  Good for EPISODIC.
      FREQUENCY_BASED   — Evict least-frequently-accessed.  Good for PROCEDURAL.
      RELEVANCE_DECAY   — Score decays over idle time.  Good for WORKING.
    """
    TTL_BASED = "ttl_based"
    FREQUENCY_BASED = "frequency_based"
    RELEVANCE_DECAY = "relevance_decay"


class RetrievalMode(str, enum.Enum):
    """Resolution strategy for memory retrieval.

    DESIGN RATIONALE:
      EXACT     — Key match (fast, deterministic).
      SEMANTIC  — Embedding similarity (non-deterministic but powerful).
      HYBRID    — Tiered: exact first, semantic fallback.
    """
    EXACT = "exact"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class PruneTrigger(str, enum.Enum):
    """What triggered a pruning operation."""
    TTL_EXPIRY = "ttl_expiry"
    CAPACITY_REACHED = "capacity_reached"
    MANUAL = "manual"
    RELEVANCE_THRESHOLD = "relevance_threshold"


# ═══════════════════════════════════════════════════════════════
# Group 2: Context Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class SafetyBounds:
    """Safety envelope for a compiled context window.

    LAW 15: Bounds enforce tenant isolation.
    RULE 3: Replay-safe — bounds are verified before context release.
    """
    tenant_id: str
    isolation_policy: str = "strict"
    cross_tenant_scope_verified: bool = False
    contains_execution_trace: bool = False
    contains_skill_data: bool = False
    contains_semantic_facts: bool = False

    def __post_init__(self) -> None:
        # Safety hash locks the isolation contract
        raw = f"{self.tenant_id}:{self.isolation_policy}:{self.cross_tenant_scope_verified}"
        self._safety_hash: str = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class TokenBudget:
    """Token allocation for a context compilation request.

    LAW 14: Same budget + same trace = same context (deterministic clipping).
    """
    max_tokens: int = 4096
    reserved_for_trace: int = 2048
    reserved_for_skills: int = 1024
    reserved_for_graph: int = 512
    reserved_for_overhead: int = 512

    def __post_init__(self) -> None:
        assert self.max_tokens >= 1024, "TokenBudget must be >= 1024"
        total = (
            self.reserved_for_trace
            + self.reserved_for_skills
            + self.reserved_for_graph
            + self.reserved_for_overhead
        )
        assert total <= self.max_tokens, (
            f"TokenBudget reservations ({total}) exceed max ({self.max_tokens})"
        )


@dataclass
class ContextWindow:
    """A compiled, safety-validated context window ready for prompt injection.

    LAW 14: Same (trace_id, tenant_id, token_budget) → same context.
    LAW 15: Bounds verify tenant isolation before release.
    RULE 3: Replay-safe — can be reconstructed deterministically.
    """
    trace_snippets: List[Dict[str, Any]] = field(default_factory=list)
    graph_context: Dict[str, Any] = field(default_factory=dict)
    skill_hints: List[Dict[str, Any]] = field(default_factory=list)
    safety_bounds: Optional[SafetyBounds] = None
    token_budget: Optional[TokenBudget] = None
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
    """Emitted when a context compilation exceeds the token budget."""
    trace_id: str
    tenant_id: str
    requested_tokens: int
    actual_tokens: int
    budget: TokenBudget
    dropped_sections: List[str]
    cognitive_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


# ═══════════════════════════════════════════════════════════════
# Group 3: Skill Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class SkillNode:
    """A single skill in the procedural memory graph.

    LAW 6: Model defined outside runtime.
    RULE 1: Procedural layer — no cross-layer imports from ExecutionCore.
    """
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
    """A known failure pattern recorded in procedural memory.

    Used by ContextCompiler to avoid recommending known-broken
    tool chains (LAW 8 recoverability).
    """
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
    """Emitted when retrieved skill does not match query intent within threshold."""
    query_intent: str
    retrieved_skill_id: str
    match_score: float
    threshold: float
    tenant_id: str
    cognitive_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


# ═══════════════════════════════════════════════════════════════
# Group 4: Forgetting Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class ForgettingPolicy:
    """A deterministic forgetting rule for a memory layer.

    DESIGN RATIONALE:
      - ttl_seconds: Entries older than this are candidates for eviction.
      - max_entries: Soft capacity cap; oldest/lowest-scored entries evicted.
      - relevance_decay_factor: Score multiplier per idle period (0 < factor ≤ 1).
      - Determinism guarantee: same input state + same policy = same eviction set.
    """
    layer: MemoryLayer
    policy_type: PruningPolicy
    ttl_seconds: Optional[float] = None
    max_entries: int = 10000
    relevance_decay_factor: float = 0.9
    tenant_id: str = ""
    cognitive_trace_id: str = ""

    def __post_init__(self) -> None:
        assert 0 < self.relevance_decay_factor <= 1.0
        self._policy_hash: str = hashlib.sha256(
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
    """Record of a single pruning decision for audit."""
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
    """Observability event emitted when a prune cycle runs."""
    layer: MemoryLayer
    evicted_count: int
    surviving_count: int
    policy_summary: str
    tenant_id: str
    cognitive_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class TenantIsolationEnforcedReport:
    """Observability event emitted when tenant isolation blocks an operation."""
    operation: str  # store / retrieve / prune / compile
    tenant_id: str
    target_tenant_id: str  # the tenant that was attempted to be crossed
    blocked: bool
    cognitive_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())


@dataclass
class MemoryEntry:
    """A single entry within the memory hierarchy.

    This is the internal storage unit for all four layers.
    It is not exposed through the protocol surface directly, but
    is documented here for implementation clarity.
    """
    key: str
    layer: MemoryLayer
    payload: Dict[str, Any]
    tenant_id: str
    isolation_policy: str = "strict"
    cognitive_trace_id: str = ""
    stored_at_ns: int = field(default_factory=lambda: time.time_ns())
    last_access_ns: int = field(default_factory=lambda: time.time_ns())
    access_count: int = 0
    ttl_seconds: Optional[float] = None
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
