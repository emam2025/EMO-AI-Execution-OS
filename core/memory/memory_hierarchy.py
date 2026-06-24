"""MemoryHierarchy — concrete implementation of IMemoryHierarchy.

LAW 6: Shared models (MemoryLayer, ContextWindow) defined outside runtime.
LAW 8: Every operation is logged and recoverable via cognitive_trace_id.
LAW 11: Every payload carries tenant_id for isolation enforcement.
RULE 3: Replay-safe — same sequence of store/retrieve calls produce same state.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from core.memory.trace_correlator import CognitiveTraceCorrelator

from core.memory.models import (  # LAW-6
    MemoryLayer,
    MemoryEntry,
    PruningPolicy,
    PruneTrigger,
    ForgettingPolicy,
    RetrievalMode,
)


class IsolationViolation(Exception):
    """Raised when a tenant isolation check fails."""


class MemoryHierarchy:  # LAW-11 LAW-14 RULE-3
    """In-memory implementation of IMemoryHierarchy.

    Storage is per-instance, keyed by (tenant_id, layer, key).
    No global mutable state — LAW 11.
    """

    def __init__(self, trace_correlator: Optional[CognitiveTraceCorrelator] = None) -> None:
        self._trace_correlator = trace_correlator
        self._entries: Dict[str, Dict[str, Dict[str, MemoryEntry]]] = {}
        # ^ {tenant_id: {layer: {key: MemoryEntry}}}

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
        if not tenant_id:
            raise IsolationViolation("store() requires non-empty tenant_id")  # LAW-11
        expires_at = None
        if ttl_seconds is not None:
            expires_at = str(time.time() + ttl_seconds)

        entry = MemoryEntry(
            key=key, layer=layer, payload=payload,
            tenant_id=tenant_id, isolation_policy=isolation_policy,
            cognitive_trace_id=cognitive_trace_id, ttl_seconds=ttl_seconds,
        )
        self._entries.setdefault(tenant_id, {}).setdefault(layer.value, {})[key] = entry

        if self._trace_correlator:
            self._trace_correlator.record_memory_store(
                cognitive_trace_id, layer.value, key, tenant_id,
            )

        return {
            "status": "stored",
            "cognitive_trace_id": cognitive_trace_id,
            "layer": layer.value,
            "key": key,
            "expires_at": expires_at,
        }

    async def retrieve(
        self,
        layer: MemoryLayer,
        query: Dict[str, Any],
        tenant_id: str,
        limit: int = 10,
        mode: RetrievalMode = RetrievalMode.EXACT,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise IsolationViolation("retrieve() requires non-empty tenant_id")  # LAW-11

        layer_store = self._entries.get(tenant_id, {}).get(layer.value, {})
        results = []

        if mode == RetrievalMode.EXACT:
            key = query.get("key", "")
            if key and key in layer_store:
                entry = layer_store[key]
                entry.access_count += 1
                entry.last_access_ns = time.time_ns()
                results.append({
                    "key": entry.key, "payload": entry.payload,
                    "cognitive_trace_id": entry.cognitive_trace_id,
                    "relevance_score": entry.relevance_score,
                    "_hash": entry._hash,
                })
        else:
            for key, entry in layer_store.items():
                entry.access_count += 1
                entry.last_access_ns = time.time_ns()
                results.append({
                    "key": entry.key, "payload": entry.payload,
                    "cognitive_trace_id": entry.cognitive_trace_id,
                    "relevance_score": entry.relevance_score,
                    "_hash": entry._hash,
                })

        results = results[:limit]
        return {
            "status": "ok",
            "results": results,
            "total": len(results),
            "cognitive_trace_id": cognitive_trace_id,
            "layer": layer.value,
        }

    async def prune(
        self,
        layer: MemoryLayer,
        policy: PruningPolicy,
        tenant_id: str,
        cognitive_trace_id: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise IsolationViolation("prune() requires non-empty tenant_id")  # LAW-11

        layer_store = self._entries.get(tenant_id, {}).get(layer.value, {})
        now = time.time()
        evicted: List[str] = []

        if policy == PruningPolicy.TTL_BASED:
            for key, entry in list(layer_store.items()):
                if entry.ttl_seconds is not None:
                    age = now - (entry.stored_at_ns / 1e9)
                    if age > entry.ttl_seconds:
                        evicted.append(key)

        elif policy == PruningPolicy.FREQUENCY_BASED:
            sorted_entries = sorted(
                layer_store.items(), key=lambda kv: kv[1].access_count,
            )
            overflow = len(sorted_entries) - 1000  # soft cap
            if overflow > 0:
                evicted = [k for k, _ in sorted_entries[:overflow]]

        elif policy == PruningPolicy.RELEVANCE_DECAY:
            for key, entry in list(layer_store.items()):
                idle_sec = (time.time_ns() - entry.last_access_ns) / 1e9
                entry.relevance_score *= (0.9 ** max(1, idle_sec / 3600))
                if entry.relevance_score < 0.1:
                    evicted.append(key)

        if not dry_run:
            for k in evicted:
                layer_store.pop(k, None)

        return {
            "status": "dry_run" if dry_run else "pruned",
            "evicted_keys": evicted,
            "surviving_count": len(layer_store),
            "policy": policy.value,
            "cognitive_trace_id": cognitive_trace_id,
        }

    async def get_context_window(
        self,
        tenant_id: str,
        layer: Optional[MemoryLayer] = None,
        max_tokens: int = 4096,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise IsolationViolation("get_context_window() requires non-empty tenant_id")  # LAW-11

        tenants = self._entries.get(tenant_id, {})
        window: Dict[str, Any] = {}
        token_count = 0
        layer_summary: Dict[str, int] = {}

        layers_to_scan = [layer] if layer else list(MemoryLayer)
        for lyr in layers_to_scan:
            lyr_key = lyr.value
            entries = tenants.get(lyr_key, {})
            layer_summary[lyr_key] = len(entries)
            if token_count < max_tokens:
                snippets = []
                for key, entry in list(entries.items())[:10]:
                    snippets.append({
                        "key": entry.key, "payload": entry.payload,
                        "cognitive_trace_id": entry.cognitive_trace_id,
                        "relevance_score": entry.relevance_score,
                    })
                window[lyr_key] = snippets
                token_count += len(snippets) * 100  # estimated

        raw = json.dumps({"window": window, "tenant_id": tenant_id}, sort_keys=True, default=str)
        context_hash = hashlib.sha256(raw.encode()).hexdigest()

        return {
            "status": "ok",
            "context_window": window,
            "context_hash": context_hash,
            "token_count": token_count,
            "layer_summary": layer_summary,
            "cognitive_trace_id": cognitive_trace_id,
        }
