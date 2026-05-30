"""
Enterprise Memory Spaces — Project/Agent isolation + Cross-Session Recall (LAW-6, LAW-23).

ProjectMemorySpace: fully isolated per-project memory with independent indexing.
AgentMemorySpace: per-agent decision/error/context store with temporal isolation.
CrossSessionRecall: intelligent retrieval across sessions with tenant/project scoping.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from releases.memory_os.core.memory.hierarchy import MemoryHierarchy
from releases.memory_os.core.memory.relevance_filter import RelevanceFilter
from releases.memory_os.core.memory.semantic_index import SemanticIndex
from releases.memory_os.core.memory.storage_adapter import SQLiteStorage
from releases.memory_os.core.models.memory import MemoryLayer, MemoryScope


class SpaceAccessError(Exception):
    """Raised when a cross-space access is attempted."""


class ProjectMemorySpace:
    """Fully isolated per-project memory subspace.

    Every operation enforces project_id matching.
    No operation can read/write data from another project.
    """

    def __init__(self, hierarchy: MemoryHierarchy, project_id: str, tenant_id: str):
        if not project_id:
            raise ValueError("project_id is required")
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        self._hierarchy = hierarchy
        self._project_id = project_id
        self._tenant_id = tenant_id

    def store(
        self,
        layer: str,
        key: str,
        payload: dict,
        agent_id: str,
        cognitive_trace_id: str,
        text: str = "",
        ttl_seconds: Optional[int] = None,
    ) -> dict:
        return self._hierarchy.store(
            layer=layer, key=key, payload=payload,
            tenant_id=self._tenant_id, project_id=self._project_id,
            agent_id=agent_id, cognitive_trace_id=cognitive_trace_id,
            ttl_seconds=ttl_seconds, text=text,
        )

    def retrieve(
        self,
        layer: str,
        query: dict,
        agent_id: str = "",
        cognitive_trace_id: str = "",
        limit: int = 10,
    ) -> List[dict]:
        q = {**query, "scope": MemoryScope.PROJECT.value}
        results = self._hierarchy.retrieve(
            layer=layer, query=q,
            tenant_id=self._tenant_id, project_id=self._project_id,
            cognitive_trace_id=cognitive_trace_id, limit=limit,
        )
        if agent_id:
            results = [r for r in results if r.get("agent_id", "") == agent_id]
        return results

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def tenant_id(self) -> str:
        return self._tenant_id


class AgentMemorySpace:
    """Per-agent memory subspace with temporal isolation.

    Stores agent decisions, errors, and context windows.
    All operations scoped by agent_id + tenant_id.
    """

    def __init__(self, hierarchy: MemoryHierarchy, agent_id: str, tenant_id: str, project_id: str = ""):
        if not agent_id:
            raise ValueError("agent_id is required")
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        self._hierarchy = hierarchy
        self._agent_id = agent_id
        self._tenant_id = tenant_id
        self._project_id = project_id

    def record_decision(
        self,
        decision: str,
        context: dict,
        cognitive_trace_id: str,
        project_id: str = "",
    ) -> dict:
        pid = project_id or self._project_id
        return self._hierarchy.store(
            layer=MemoryLayer.WORKING.value, key=f"decision-{uuid.uuid4().hex[:8]}",
            payload={"decision": decision, "context": context},
            tenant_id=self._tenant_id, project_id=pid,
            agent_id=self._agent_id, cognitive_trace_id=cognitive_trace_id,
            scope=MemoryScope.AGENT.value, text=decision,
        )

    def record_error(
        self,
        error: str,
        trace: dict,
        cognitive_trace_id: str,
        project_id: str = "",
    ) -> dict:
        pid = project_id or self._project_id
        return self._hierarchy.store(
            layer=MemoryLayer.EPISODIC.value, key=f"error-{uuid.uuid4().hex[:8]}",
            payload={"error": error, "trace": trace},
            tenant_id=self._tenant_id, project_id=pid,
            agent_id=self._agent_id, cognitive_trace_id=cognitive_trace_id,
            scope=MemoryScope.AGENT.value, text=f"agent error: {error}",
        )

    def get_session_context(
        self,
        cognitive_trace_id: str,
        limit: int = 20,
        time_window_hours: float = 24.0,
    ) -> List[dict]:
        now = time.time()
        window_seconds = time_window_hours * 3600
        cutoff = now - window_seconds
        all_results = []
        for layer in MemoryLayer:
            results = self._hierarchy.retrieve(
                layer=layer.value,
                query={"scope": MemoryScope.AGENT.value, "text": ""},
                tenant_id=self._tenant_id,
                project_id=self._project_id,
                cognitive_trace_id=cognitive_trace_id,
                limit=limit,
            )
            for r in results:
                if r.get("agent_id", "") != self._agent_id:
                    continue
                created = r.get("created_at", 0)
                if created >= cutoff:
                    all_results.append(r)
        return all_results[:limit]

    @property
    def agent_id(self) -> str:
        return self._agent_id


class CrossSessionRecall:
    """Intelligent recall across sessions with temporal and relevance filtering.

    Combines entries from multiple sessions, deduplicates, ranks by relevance,
    and enforces tenant/project isolation.
    """

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        relevance_filter: Optional[RelevanceFilter] = None,
    ):
        self._hierarchy = hierarchy
        self._relevance_filter = relevance_filter or RelevanceFilter()

    def recall(
        self,
        query: str,
        tenant_id: str,
        project_id: str = "",
        scope: str = "project",
        time_window_days: float = 90.0,
        limit: int = 20,
        min_relevance: float = 0.05,
    ) -> dict:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        cutoff = time.time() - (time_window_days * 86400)
        all_entries: List[dict] = []
        layers = [l.value for l in MemoryLayer]
        for layer in layers:
            q = {"scope": scope, "text": query, "semantic_threshold": 0.0}
            results = self._hierarchy.retrieve(
                layer=layer, query=q,
                tenant_id=tenant_id, project_id=project_id,
                cognitive_trace_id="recall-session",
                limit=limit * 2,
            )
            for r in results:
                created = r.get("created_at", 0)
                if created >= cutoff:
                    r["_layer"] = layer
                    all_entries.append(r)
        seen_hashes: set = set()
        unique: List[dict] = []
        for e in all_entries:
            h = str(e.get("content_hash", e.get("entry_id", "")))
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            unique.append(e)
        self._relevance_filter.set_min_relevance(min_relevance)
        filtered = self._relevance_filter.filter_low_relevance(unique)
        filtered.sort(key=lambda x: x.get("relevance_score", 0.0), reverse=True)
        return {
            "query": query,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "scope": scope,
            "sessions_scanned": len(set(e.get("cognitive_trace_id", "") for e in unique)),
            "total_candidates": len(all_entries),
            "unique_entries": len(unique),
            "entries_returned": min(len(filtered), limit),
            "entries": filtered[:limit],
        }
