"""ProjectMemory — per-project memory namespace with TTL, isolation, and audit.

Each project gets an isolated namespace within the MemoryHierarchy's PROJECT layer.
All operations carry cognitive_trace_id for LAW 8 auditability.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.memory.memory_hierarchy import MemoryHierarchy
from core.memory.models import MemoryLayer, RetrievalMode
from core.memory.trace_correlator import CognitiveTraceCorrelator


@dataclass
class ProjectMemoryEntry:
    project_id: str
    key: str
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    cognitive_trace_id: str = ""
    created_at_ns: int = field(default_factory=lambda: time.time_ns())
    updated_at_ns: int = field(default_factory=lambda: time.time_ns())
    access_count: int = 0
    relevance_score: float = 1.0


@dataclass
class ProjectSummary:
    project_id: str
    entry_count: int
    total_access_count: int
    oldest_entry_ns: int
    newest_entry_ns: int
    cognitive_trace_id: str = ""


class ProjectMemory:
    """Per-project memory — each project gets an isolated namespace.

    Stores data in the MemoryHierarchy PROJECT layer under composite keys
    ``{project_id}:{key}``.  All operations delegate to MemoryHierarchy for
    tenant-isolated, TTL-aware, traceable persistence.
    """

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        trace_correlator: Optional[CognitiveTraceCorrelator] = None,
    ) -> None:
        self._hierarchy = hierarchy
        self._trace_correlator = trace_correlator or CognitiveTraceCorrelator()
        self._project_metadata: Dict[str, Dict[str, ProjectMemoryEntry]] = {}

    def _project_key(self, project_id: str, key: str) -> str:
        return f"{project_id}:{key}"

    def _parse_project_key(self, compound: str) -> tuple[str, str]:
        parts = compound.split(":", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return "", parts[0]

    async def store(
        self,
        project_id: str,
        key: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not project_id:
            raise ValueError("project_id is required")
        if not key:
            raise ValueError("key is required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or project_id, f"pm:{project_id}",
        )
        compound_key = self._project_key(project_id, key)

        result = await self._hierarchy.store(
            layer=MemoryLayer.PROJECT,
            key=compound_key,
            payload=payload,
            tenant_id=tenant_id or project_id,
            isolation_policy="strict",
            cognitive_trace_id=trace_id,
            ttl_seconds=ttl_seconds,
        )

        self._project_metadata.setdefault(project_id, {})[key] = ProjectMemoryEntry(
            project_id=project_id,
            key=key,
            payload=payload,
            metadata=metadata or {},
            cognitive_trace_id=trace_id,
        )

        return {
            "status": "stored",
            "project_id": project_id,
            "key": key,
            "ttl_seconds": ttl_seconds,
            "cognitive_trace_id": trace_id,
            "hierarchy_result": result,
        }

    async def retrieve(
        self,
        project_id: str,
        key: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not project_id or not key:
            raise ValueError("project_id and key are required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or project_id, f"pm:{project_id}:retrieve",
        )
        compound_key = self._project_key(project_id, key)

        result = await self._hierarchy.retrieve(
            layer=MemoryLayer.PROJECT,
            query={"key": compound_key},
            tenant_id=tenant_id or project_id,
            mode=RetrievalMode.EXACT,
            cognitive_trace_id=trace_id,
            limit=1,
        )

        if key in self._project_metadata.get(project_id, {}):
            self._project_metadata[project_id][key].access_count += 1
            self._project_metadata[project_id][key].updated_at_ns = time.time_ns()

        return {
            "status": "ok" if result["total"] > 0 else "not_found",
            "project_id": project_id,
            "key": key,
            "result": result["results"][0] if result["total"] > 0 else None,
            "cognitive_trace_id": trace_id,
        }

    async def search(
        self,
        project_id: str,
        query_text: str = "",
        limit: int = 10,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not project_id:
            raise ValueError("project_id is required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or project_id, f"pm:{project_id}:search",
        )

        result = await self._hierarchy.retrieve(
            layer=MemoryLayer.PROJECT,
            query={"key": ""},
            tenant_id=tenant_id or project_id,
            mode=RetrievalMode.HYBRID,
            cognitive_trace_id=trace_id,
            limit=limit,
        )

        all_results = result["results"]
        if query_text:
            query_lower = query_text.lower()
            filtered = []
            for r in all_results:
                compound = r.get("key", "")
                _, entry_key = self._parse_project_key(compound)
                payload_str = str(r.get("payload", {})).lower()
                key_matches = query_lower in entry_key.lower()
                payload_matches = query_lower in payload_str
                if key_matches or payload_matches:
                    r["_match_reason"] = "key" if key_matches else "payload"
                    filtered.append(r)
            results = filtered[:limit]
        else:
            results = all_results[:limit]

        return {
            "status": "ok",
            "project_id": project_id,
            "query": query_text,
            "results": results,
            "total": len(results),
            "cognitive_trace_id": trace_id,
        }

    async def list_projects(
        self,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        summaries: List[ProjectSummary] = []
        for pid, entries in self._project_metadata.items():
            if not entries:
                continue
            timestamps = [e.created_at_ns for e in entries.values()]
            summaries.append(ProjectSummary(
                project_id=pid,
                entry_count=len(entries),
                total_access_count=sum(e.access_count for e in entries.values()),
                oldest_entry_ns=min(timestamps),
                newest_entry_ns=max(timestamps),
            ))
        summaries.sort(key=lambda s: s.project_id)

        return {
            "status": "ok",
            "projects": [{
                "project_id": s.project_id,
                "entry_count": s.entry_count,
                "total_access_count": s.total_access_count,
                "oldest_entry": s.oldest_entry_ns,
                "newest_entry": s.newest_entry_ns,
            } for s in summaries],
            "total_projects": len(summaries),
            "cognitive_trace_id": cognitive_trace_id or "",
        }

    async def delete_project(
        self,
        project_id: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not project_id:
            raise ValueError("project_id is required")

        self._project_metadata.pop(project_id, None)

        return {
            "status": "deleted",
            "project_id": project_id,
            "cognitive_trace_id": cognitive_trace_id or "",
        }

    async def get_stats(
        self,
        project_id: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not project_id:
            raise ValueError("project_id is required")

        entries = self._project_metadata.get(project_id, {})
        if not entries:
            return {
                "status": "not_found",
                "project_id": project_id,
                "cognitive_trace_id": cognitive_trace_id or "",
            }

        timestamps = [e.created_at_ns for e in entries.values()]
        keys = list(entries.keys())

        return {
            "status": "ok",
            "project_id": project_id,
            "entry_count": len(entries),
            "total_access_count": sum(e.access_count for e in entries.values()),
            "keys": keys,
            "oldest_entry_ns": min(timestamps),
            "newest_entry_ns": max(timestamps),
            "cognitive_trace_id": cognitive_trace_id or "",
        }

    async def delete_key(
        self,
        project_id: str,
        key: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not project_id or not key:
            raise ValueError("project_id and key are required")

        self._project_metadata.get(project_id, {}).pop(key, None)

        return {
            "status": "deleted",
            "project_id": project_id,
            "key": key,
            "cognitive_trace_id": cognitive_trace_id or "",
        }
