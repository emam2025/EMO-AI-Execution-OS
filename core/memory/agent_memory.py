"""AgentMemory — per-agent memory namespace with skill integration, TTL, audit.

Each agent gets an isolated namespace within the MemoryHierarchy's AGENT layer.
Optionally integrates with SkillGraphManager to track skill usage per agent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.memory.memory_hierarchy import MemoryHierarchy
from core.memory.models import MemoryLayer, RetrievalMode
from core.memory.skill_graph_manager import SkillGraphManager
from core.memory.trace_correlator import CognitiveTraceCorrelator


@dataclass
class AgentMemoryEntry:
    agent_id: str
    key: str
    payload: Dict[str, Any]
    skill_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    cognitive_trace_id: str = ""
    created_at_ns: int = field(default_factory=lambda: time.time_ns())
    updated_at_ns: int = field(default_factory=lambda: time.time_ns())
    access_count: int = 0
    relevance_score: float = 1.0


@dataclass
class AgentSkillSummary:
    agent_id: str
    skills: Dict[str, int]
    total_skill_refs: int
    cognitive_trace_id: str = ""


@dataclass
class AgentSummary:
    agent_id: str
    entry_count: int
    total_access_count: int
    skill_count: int
    oldest_entry_ns: int
    newest_entry_ns: int
    cognitive_trace_id: str = ""


class AgentMemory:
    """Per-agent memory — each agent gets an isolated namespace.

    Stores data in the MemoryHierarchy AGENT layer under composite keys
    ``{agent_id}:{key}``.  Optionally integrates with SkillGraphManager
    to track which skills each agent references.
    """

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        skill_graph: Optional[SkillGraphManager] = None,
        trace_correlator: Optional[CognitiveTraceCorrelator] = None,
    ) -> None:
        self._hierarchy = hierarchy
        self._skill_graph = skill_graph
        self._trace_correlator = trace_correlator or CognitiveTraceCorrelator()
        self._agent_metadata: Dict[str, Dict[str, AgentMemoryEntry]] = {}
        self._agent_skills: Dict[str, Dict[str, int]] = {}

    def _agent_key(self, agent_id: str, key: str) -> str:
        return f"{agent_id}:{key}"

    def _parse_agent_key(self, compound: str) -> tuple[str, str]:
        parts = compound.split(":", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return "", parts[0]

    def _track_skill(self, agent_id: str, skill_id: str) -> None:
        if not skill_id:
            return
        self._agent_skills.setdefault(agent_id, {})
        self._agent_skills[agent_id][skill_id] = (
            self._agent_skills[agent_id].get(skill_id, 0) + 1
        )

    async def store(
        self,
        agent_id: str,
        key: str,
        payload: Dict[str, Any],
        skill_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id is required")
        if not key:
            raise ValueError("key is required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or agent_id, f"am:{agent_id}",
        )
        compound_key = self._agent_key(agent_id, key)

        result = await self._hierarchy.store(
            layer=MemoryLayer.AGENT,
            key=compound_key,
            payload=payload,
            tenant_id=tenant_id or agent_id,
            isolation_policy="strict",
            cognitive_trace_id=trace_id,
            ttl_seconds=ttl_seconds,
        )

        self._agent_metadata.setdefault(agent_id, {})[key] = AgentMemoryEntry(
            agent_id=agent_id,
            key=key,
            payload=payload,
            skill_id=skill_id,
            metadata=metadata or {},
            cognitive_trace_id=trace_id,
        )

        self._track_skill(agent_id, skill_id)

        return {
            "status": "stored",
            "agent_id": agent_id,
            "key": key,
            "skill_id": skill_id,
            "ttl_seconds": ttl_seconds,
            "cognitive_trace_id": trace_id,
            "hierarchy_result": result,
        }

    async def retrieve(
        self,
        agent_id: str,
        key: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id or not key:
            raise ValueError("agent_id and key are required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or agent_id, f"am:{agent_id}:retrieve",
        )
        compound_key = self._agent_key(agent_id, key)

        result = await self._hierarchy.retrieve(
            layer=MemoryLayer.AGENT,
            query={"key": compound_key},
            tenant_id=tenant_id or agent_id,
            mode=RetrievalMode.EXACT,
            cognitive_trace_id=trace_id,
            limit=1,
        )

        if key in self._agent_metadata.get(agent_id, {}):
            self._agent_metadata[agent_id][key].access_count += 1
            self._agent_metadata[agent_id][key].updated_at_ns = time.time_ns()

        return {
            "status": "ok" if result["total"] > 0 else "not_found",
            "agent_id": agent_id,
            "key": key,
            "result": result["results"][0] if result["total"] > 0 else None,
            "cognitive_trace_id": trace_id,
        }

    async def search(
        self,
        agent_id: str,
        query_text: str = "",
        skill_id: str = "",
        limit: int = 10,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id is required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or agent_id, f"am:{agent_id}:search",
        )

        result = await self._hierarchy.retrieve(
            layer=MemoryLayer.AGENT,
            query={"key": ""},
            tenant_id=tenant_id or agent_id,
            mode=RetrievalMode.HYBRID,
            cognitive_trace_id=trace_id,
            limit=limit * 3,
        )

        all_results = result["results"]
        filtered = []

        for r in all_results:
            compound = r.get("key", "")
            _, entry_key = self._parse_agent_key(compound)
            meta = self._agent_metadata.get(agent_id, {}).get(entry_key)

            if skill_id and meta and meta.skill_id != skill_id:
                continue

            if query_text:
                query_lower = query_text.lower()
                key_match = query_lower in entry_key.lower()
                payload_str = str(r.get("payload", {})).lower()
                payload_match = query_lower in payload_str
                if not key_match and not payload_match:
                    continue
                r["_match_reason"] = "key" if key_match else "payload"

            filtered.append(r)

        results = filtered[:limit]
        return {
            "status": "ok",
            "agent_id": agent_id,
            "query": query_text,
            "skill_filter": skill_id,
            "results": results,
            "total": len(results),
            "cognitive_trace_id": trace_id,
        }

    async def search_by_skill(
        self,
        agent_id: str,
        skill_id: str,
        limit: int = 10,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        return await self.search(
            agent_id=agent_id,
            query_text="",
            skill_id=skill_id,
            limit=limit,
            tenant_id=tenant_id,
            cognitive_trace_id=cognitive_trace_id,
        )

    async def get_skill_summary(
        self,
        agent_id: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id is required")

        skills = self._agent_skills.get(agent_id, {})
        total = sum(skills.values())

        return {
            "status": "ok",
            "agent_id": agent_id,
            "skills": dict(sorted(skills.items())),
            "total_skill_refs": total,
            "unique_skills": len(skills),
            "cognitive_trace_id": cognitive_trace_id or "",
        }

    async def list_agents(
        self,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        summaries: List[AgentSummary] = []
        for aid, entries in self._agent_metadata.items():
            if not entries:
                continue
            timestamps = [e.created_at_ns for e in entries.values()]
            skills = self._agent_skills.get(aid, {})
            summaries.append(AgentSummary(
                agent_id=aid,
                entry_count=len(entries),
                total_access_count=sum(e.access_count for e in entries.values()),
                skill_count=len(skills),
                oldest_entry_ns=min(timestamps),
                newest_entry_ns=max(timestamps),
            ))
        summaries.sort(key=lambda s: s.agent_id)

        return {
            "status": "ok",
            "agents": [{
                "agent_id": s.agent_id,
                "entry_count": s.entry_count,
                "total_access_count": s.total_access_count,
                "skill_count": s.skill_count,
                "oldest_entry": s.oldest_entry_ns,
                "newest_entry": s.newest_entry_ns,
            } for s in summaries],
            "total_agents": len(summaries),
            "cognitive_trace_id": cognitive_trace_id or "",
        }

    async def delete_agent(
        self,
        agent_id: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id is required")

        self._agent_metadata.pop(agent_id, None)
        self._agent_skills.pop(agent_id, None)

        return {
            "status": "deleted",
            "agent_id": agent_id,
            "cognitive_trace_id": cognitive_trace_id or "",
        }

    async def get_stats(
        self,
        agent_id: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id is required")

        entries = self._agent_metadata.get(agent_id, {})
        if not entries:
            return {
                "status": "not_found",
                "agent_id": agent_id,
                "cognitive_trace_id": cognitive_trace_id or "",
            }

        timestamps = [e.created_at_ns for e in entries.values()]
        keys = list(entries.keys())
        skills = self._agent_skills.get(agent_id, {})

        return {
            "status": "ok",
            "agent_id": agent_id,
            "entry_count": len(entries),
            "total_access_count": sum(e.access_count for e in entries.values()),
            "keys": keys,
            "skills": dict(sorted(skills.items())),
            "oldest_entry_ns": min(timestamps),
            "newest_entry_ns": max(timestamps),
            "cognitive_trace_id": cognitive_trace_id or "",
        }

    async def delete_key(
        self,
        agent_id: str,
        key: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id or not key:
            raise ValueError("agent_id and key are required")

        self._agent_metadata.get(agent_id, {}).pop(key, None)

        return {
            "status": "deleted",
            "agent_id": agent_id,
            "key": key,
            "cognitive_trace_id": cognitive_trace_id or "",
        }
