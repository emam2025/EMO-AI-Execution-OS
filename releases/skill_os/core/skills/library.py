"""
Skill Library — versioned storage, query, and version history.

Instance-level storage (no global state). All operations enforce
tenant_id scoping (LAW-6, LAW-11).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from releases.skill_os.core.models.skills import (
    ExecutionBlueprint,
    SkillDomain,
    SkillEvolutionRecord,
    SkillNode,
    SkillStoreEntry,
    SkillTier,
    SkillVersion,
)


class SkillLibrary:
    """Versioned skill storage with query and history capabilities.

    LAW-6: every public method requires tenant_id.
    LAW-11: every query filters by tenant_id.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, SkillStoreEntry] = {}

    # ── public API ─────────────────────────────────────────────

    def store(
        self,
        skill_name: str,
        pattern_hash: str,
        confidence_score: float,
        tenant_id: str,
        project_id: str = "",
        source_trace_id: str = "",
        domain: SkillDomain = SkillDomain.UNKNOWN,
        tool_sequence: Optional[List[str]] = None,
    ) -> str:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        skill_id = f"sk-{uuid.uuid4().hex[:16]}"
        tier = SkillTier.VERIFIED if confidence_score >= 0.7 else SkillTier.DRAFT
        now = time.time()
        node = SkillNode(
            skill_id=skill_id,
            tenant_id=tenant_id,
            project_id=project_id,
            skill_name=skill_name,
            pattern_hash=pattern_hash,
            confidence_score=confidence_score,
            tier=tier,
            domain=domain,
            source_trace_ids=[source_trace_id] if source_trace_id else [],
        )
        blueprint_id = f"bp-{uuid.uuid4().hex[:12]}"
        blueprint = ExecutionBlueprint(
            blueprint_id=blueprint_id,
            skill_id=skill_id,
            tenant_id=tenant_id,
            tool_sequence=tool_sequence or [],
        )
        version_id = f"ver-{uuid.uuid4().hex[:12]}"
        version = SkillVersion(
            version_id=version_id,
            skill_id=skill_id,
            tenant_id=tenant_id,
            version=1,
            tier=tier,
            pattern_hash=pattern_hash,
            confidence_score=confidence_score,
            tool_sequence=tool_sequence or [],
        )
        entry_id = f"se-{uuid.uuid4().hex[:12]}"
        raw = json.dumps(node.__dict__, sort_keys=True, default=str)
        checksum = hashlib.sha256(raw.encode()).hexdigest()[:16]
        entry = SkillStoreEntry(
            entry_id=entry_id,
            skill=node,
            blueprints=[blueprint],
            evolution_history=[],
            versions=[version],
            checksum=checksum,
        )
        self._entries[skill_id] = entry
        return skill_id

    def query(
        self,
        tenant_id: str,
        domain: Optional[SkillDomain] = None,
        tool: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> List[SkillNode]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        results: List[SkillNode] = []
        for entry in self._entries.values():
            node = entry.skill
            if node.tenant_id != tenant_id:
                continue
            if node.tier == SkillTier.DEPRECATED:
                continue
            if domain and node.domain != domain:
                continue
            if tool:
                bp_tools = [b.tool_sequence for b in entry.blueprints]
                if not any(tool in tools for tools in bp_tools):
                    continue
            if node.confidence_score < min_confidence:
                continue
            results.append(node)
        results.sort(key=lambda n: (n.tier.value, n.confidence_score), reverse=True)
        return results[:limit]

    def get_version_history(
        self,
        skill_id: str,
        tenant_id: str,
    ) -> List[SkillVersion]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        entry = self._entries.get(skill_id)
        if not entry:
            raise KeyError(f"Skill not found: {skill_id}")
        if entry.skill.tenant_id != tenant_id:
            raise KeyError(f"Skill not found for tenant: {skill_id}")
        return list(entry.versions)

    def get(
        self,
        skill_id: str,
        tenant_id: str,
    ) -> SkillNode:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        entry = self._entries.get(skill_id)
        if not entry:
            raise KeyError(f"Skill not found: {skill_id}")
        if entry.skill.tenant_id != tenant_id:
            raise KeyError(f"Skill not found for tenant: {skill_id}")
        return entry.skill

    def get_blueprints(
        self,
        skill_id: str,
        tenant_id: str,
    ) -> List[ExecutionBlueprint]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        entry = self._entries.get(skill_id)
        if not entry:
            raise KeyError(f"Skill not found: {skill_id}")
        if entry.skill.tenant_id != tenant_id:
            raise KeyError(f"Skill not found for tenant: {skill_id}")
        return list(entry.blueprints)

    def count(self, tenant_id: str) -> int:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        return sum(1 for e in self._entries.values() if e.skill.tenant_id == tenant_id)

    def get_evolution_history(
        self,
        skill_id: str,
        tenant_id: str,
    ) -> List[SkillEvolutionRecord]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        entry = self._entries.get(skill_id)
        if not entry:
            raise KeyError(f"Skill not found: {skill_id}")
        if entry.skill.tenant_id != tenant_id:
            raise KeyError(f"Skill not found for tenant: {skill_id}")
        return list(entry.evolution_history)

    # ── internal (for SkillEvolutionManager) ───────────────────

    def _update_tier(
        self,
        skill_id: str,
        tenant_id: str,
        new_tier: SkillTier,
        record: SkillEvolutionRecord,
    ) -> SkillNode:
        entry = self._entries.get(skill_id)
        if not entry:
            raise KeyError(f"Skill not found: {skill_id}")
        if entry.skill.tenant_id != tenant_id:
            raise KeyError(f"Skill not found for tenant: {skill_id}")
        old_tier = entry.skill.tier
        entry.skill.tier = new_tier
        entry.skill.updated_at = time.time()
        entry.evolution_history.append(record)
        next_ver = len(entry.versions) + 1
        version = SkillVersion(
            version_id=f"ver-{uuid.uuid4().hex[:12]}",
            skill_id=skill_id,
            tenant_id=tenant_id,
            version=next_ver,
            tier=new_tier,
            pattern_hash=entry.skill.pattern_hash,
            confidence_score=entry.skill.confidence_score,
            created_at=time.time(),
        )
        entry.versions.append(version)
        entry.skill.success_rate = entry.skill.success_rate or 0.0
        entry.skill.execution_count += 1
        return entry.skill

    def _entry_exists(self, skill_id: str, tenant_id: str) -> bool:
        entry = self._entries.get(skill_id)
        return entry is not None and entry.skill.tenant_id == tenant_id
