"""Phase L — Cognitive Memory Layer Protocols.

Design overview:
  Phase L introduces a structured memory hierarchy that sits above the
  stabilised Runtime (F1/J2/I1/F4).  It defines three protocol surfaces:

    1. IMemoryHierarchy   —  store / retrieve / prune across memory layers
    2. IContextCompiler   —  compress ExecutionTrace into prompt-ready context
    3. ISkillGraphManager —  record & retrieve procedural skill nodes

  The protocols are PURE DESIGN CONTRACTS.  No implementation lives in
  core/; no runtime mutation occurs.  They are the architectural blueprint
  for Phase L implementation.

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
  - RULE 3 (Replay safety)
  - artifacts/design/j2/protocols/01_enterprise_protocols.py
  - artifacts/design/phase_l/models/02_memory_and_context_models.py

NON-NEGOTIABLE:
  - Every store/retrieve operation MUST carry cognitive_trace_id for full audit.
  - Every layer routing decision MUST check tenant isolation (tenant_id + isolation_policy).
  - ContextCompiler MUST reject cross-tenant context without explicit scope_verified.
  - No protocol method may return or accept runtime-internal types (ExecutionEvent,
    DAG, Engine) — only plain dicts and phase_l model types.
  - Forgetting policies MUST be deterministic: same trace + same policy = same prune decision.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════
# Shared Enums (design self-contained; implementations should
# import from 02_memory_and_context_models.py)
# ═══════════════════════════════════════════════════════════════

class MemoryLayer(str, enum.Enum):
    """The four layers of the Cognitive Memory hierarchy."""
    WORKING = "working"          # Volatile, session-scoped
    EPISODIC = "episodic"        # Trace-backed, execution history
    PROCEDURAL = "procedural"    # Skill / plans / failure patterns
    SEMANTIC = "semantic"        # Graph facts, static knowledge


class PruningPolicy(str, enum.Enum):
    """Deterministic forgetting strategies."""
    TTL_BASED = "ttl_based"          # Expire after a time-to-live
    FREQUENCY_BASED = "frequency_based"  # Evict least-frequently-accessed
    RELEVANCE_DECAY = "relevance_decay"  # Decay score over time


class RetrievalMode(str, enum.Enum):
    """How the memory hierarchy resolves a retrieval query."""
    EXACT = "exact"       # Must match key exactly
    SEMANTIC = "semantic"  # Embedding / similarity search
    HYBRID = "hybrid"     # Combine exact + semantic


# ═══════════════════════════════════════════════════════════════
# IMemoryHierarchy
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class IMemoryHierarchy(Protocol):
    """The root surface for reading and writing the memory hierarchy.

    LAW 6: Shared models (MemoryLayer, ContextWindow) defined outside runtime.
    LAW 8: Every operation is logged and recoverable via cognitive_trace_id.
    LAW 11: Every payload carries tenant_id for isolation enforcement.
    RULE 3: Replay-safe — same sequence of store/retrieve calls with same
            arguments MUST produce the same state modulo pruning.
    """

    async def store(
        self,
        layer: MemoryLayer,
        key: str,
        payload: Dict[str, Any],
        tenant_id: str,
        isolation_policy: str,
        cognitive_trace_id: str,
        ttl_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Store a payload in the given memory layer.

        Args:
            layer:             Target memory layer.
            key:               Unique key within (tenant_id, layer).
            payload:           Arbitrary data dict.
            tenant_id:         Owning tenant (LAW 11 isolation check).
            isolation_policy:  Isolation mode ("strict" / "shared").
            cognitive_trace_id:Audit trail identifier.
            ttl_seconds:       Optional TTL for automatic pruning.

        Returns:
            {"status": "stored", "cognitive_trace_id": str,
             "layer": str, "key": str, "expires_at": str|None}

        Raises:
            IsolationViolation: If tenant isolation check fails.
        """
        ...

    async def retrieve(
        self,
        layer: MemoryLayer,
        query: Dict[str, Any],
        tenant_id: str,
        limit: int = 10,
        mode: RetrievalMode = RetrievalMode.EXACT,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Retrieve entries from a memory layer.

        Args:
            layer:              Source layer.
            query:              Query parameters (key, intent, embedding, etc.).
            tenant_id:          Tenant scope filter.
            limit:              Max results.
            mode:               Retrieval strategy (EXACT / SEMANTIC / HYBRID).
            cognitive_trace_id: Audit trail identifier.

        Returns:
            {"status": "ok", "results": list[dict], "total": int,
             "cognitive_trace_id": str, "layer": str}
        """
        ...

    async def prune(
        self,
        layer: MemoryLayer,
        policy: PruningPolicy,
        tenant_id: str,
        cognitive_trace_id: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Apply a forgetting policy to a memory layer.

        Determinism guarantee: same layer state + same policy = same
        set of evicted keys across runs.

        Args:
            layer:              Target layer.
            policy:             Forgetting strategy.
            tenant_id:          Tenant scope.
            cognitive_trace_id: Audit trail.
            dry_run:            If True, report what WOULD be pruned.

        Returns:
            {"status": "pruned"|"dry_run", "evicted_keys": list[str],
             "surviving_count": int, "policy": str, "cognitive_trace_id": str}
        """
        ...

    async def get_context_window(
        self,
        tenant_id: str,
        layer: Optional[MemoryLayer] = None,
        max_tokens: int = 4096,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Return a consolidated context window from one or all layers.

        Args:
            tenant_id:          Tenant scope.
            layer:              Specific layer, or None for cross-layer.
            max_tokens:         Token budget for the window.
            cognitive_trace_id: Audit trail.

        Returns:
            {"status": "ok", "context_window": dict, "token_count": int,
             "layer_summary": dict[str, int], "cognitive_trace_id": str}
        """
        ...


# ═══════════════════════════════════════════════════════════════
# IContextCompiler
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class IContextCompiler(Protocol):
    """Compresses runtime execution traces into prompt-ready context.

    LAW 14: Compiler must produce the SAME context for same
            (trace_id, tenant_id, max_tokens) inputs — deterministic retrieval.
    LAW 15: Never leaks cross-tenant context (every window is scoped to
            a single tenant_id verified via scope_verified flag).
    RULE 3: Replay-safe — context reconstruction must be idempotent.
    """

    async def compress_trace_to_context(
        self,
        trace_id: str,
        tenant_id: str,
        max_tokens: int = 4096,
        scope_verified: bool = False,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Compress an execution trace into a prompt-ready context dict.

        Determinism:  same trace_id + same max_tokens = same output
                      (modulo time-sensitive metadata).

        Args:
            trace_id:           The execution trace to compress.
            tenant_id:          Tenant scope (checked for isolation).
            max_tokens:         Token budget for compression.
            scope_verified:     MUST be True for cross-tenant access.
            cognitive_trace_id: Audit trail.

        Returns:
            {"status": "ok", "context": dict, "token_count": int,
             "compression_ratio": float, "cognitive_trace_id": str}
        """
        ...

    async def inject_runtime_intelligence(
        self,
        context: Dict[str, Any],
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Augment a context window with live intelligence state.

        Args:
            context:            Context dict from compress_trace_to_context().
            tenant_id:          Tenant scope.
            cognitive_trace_id: Audit trail.

        Returns:
            {"status": "ok", "augmented_context": dict,
             "injected_signals": list[str], "cognitive_trace_id": str}
        """
        ...

    async def validate_boundary_safety(
        self,
        context: Dict[str, Any],
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Verify that a compiled context contains no cross-tenant data.

        This is the enforcement point for LAW 15 / RULE 3.

        Args:
            context:            Compiled context to validate.
            tenant_id:          Expected owning tenant.
            cognitive_trace_id: Audit trail.

        Returns:
            {"status": "safe"|"violation", "violations": list[str],
             "cognitive_trace_id": str}
        """
        ...


# ═══════════════════════════════════════════════════════════════
# ISkillGraphManager
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class ISkillGraphManager(Protocol):
    """Governs the Procedural memory layer — tool chains, plans, patterns.

    LAW 6: SkillNode model is defined outside runtime.
    LAW 8: Every mutation is recoverable via cognitive_trace_id.
    RULE 1: Skill graph uses its own layer (PROCEDURAL) — no cross-layer imports.
    """

    async def record_successful_plan(
        self,
        dag_id: str,
        plan_hash: str,
        tenant_id: str,
        intent: str,
        tool_chain: List[Dict[str, Any]],
        cost_units: float,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Record a successful execution plan as a procedural skill.

        Args:
            dag_id:             Executed DAG identifier.
            plan_hash:          Deterministic plan hash (replay safety).
            tenant_id:          Owning tenant.
            intent:             Natural-language intent this plan satisfied.
            tool_chain:         Ordered list of tool calls that succeeded.
            cost_units:         Execution cost for cost-profile.
            cognitive_trace_id: Audit trail.

        Returns:
            {"status": "recorded", "skill_id": str,
             "cognitive_trace_id": str}
        """
        ...

    async def retrieve_skill(
        self,
        query_intent: str,
        tenant_id: str,
        top_k: int = 3,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Retrieve the best-matching skills for a given intent.

        Args:
            query_intent:       Natural-language or structured intent query.
            tenant_id:          Tenant scope.
            top_k:              Max skills to return.
            cognitive_trace_id: Audit trail.

        Returns:
            {"status": "ok", "skills": list[dict], "total": int,
             "cognitive_trace_id": str}
        """
        ...

    async def update_procedural_weight(
        self,
        skill_id: str,
        feedback: float,
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Update a skill node's weight based on execution feedback.

        Args:
            skill_id:           Target skill.
            feedback:           Rating (-1.0 to 1.0).
            tenant_id:          Tenant scope.
            cognitive_trace_id: Audit trail.

        Returns:
            {"status": "updated", "skill_id": str,
             "new_success_rate": float, "cognitive_trace_id": str}
        """
        ...

    async def record_failure_pattern(
        self,
        dag_id: str,
        failure_hash: str,
        tenant_id: str,
        failure_signal: str,
        tool_chain: List[Dict[str, Any]],
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Record a known failure pattern to avoid re-execution.

        Args:
            dag_id:             Failed DAG identifier.
            failure_hash:       Deterministic failure hash.
            tenant_id:          Tenant scope.
            failure_signal:     Error signal / exception type.
            tool_chain:         Tool chain at failure point.
            cognitive_trace_id: Audit trail.

        Returns:
            {"status": "recorded", "pattern_id": str,
             "cognitive_trace_id": str}
        """
        ...
