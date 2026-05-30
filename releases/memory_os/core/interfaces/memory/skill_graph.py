"""
ISkillGraphManager — Memory OS Protocol Interface (LAW-6, LAW-11).

Defines the contract for skill graph recording and retrieval.
No implementation — interface only.

LAW-6: Every skill operation MUST carry tenant_id.
LAW-11: Every skill operation MUST carry cognitive_trace_id.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ISkillGraphManager(Protocol):
    """Skill graph with tenant-scoped recording and retrieval."""

    def record(
        self,
        skill_name: str,
        pattern: dict,
        tenant_id: str,
        cognitive_trace_id: str,
        weight: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Record a learned skill in the graph.

        Args:
            skill_name: Unique name for the skill.
            pattern: The execution pattern / solution structure.
            tenant_id: MUST scope to tenant (LAW-6).
            cognitive_trace_id: MUST propagate (LAW-11).
            weight: Initial importance weight.
            metadata: Optional enrichment data.

        Returns:
            {"skill_id": str, "recorded": bool, "weight": float}
        """
        ...

    def retrieve(
        self,
        query: dict,
        tenant_id: str,
        cognitive_trace_id: str,
        limit: int = 5,
    ) -> List[dict]:
        """Find skills matching a query.

        Args:
            query: Search/filter criteria.
            tenant_id: MUST filter to tenant (LAW-6).
            cognitive_trace_id: MUST propagate (LAW-11).
            limit: Maximum results.

        Returns:
            List of skill dicts with name, pattern, weight, usage_count.
        """
        ...

    def update_weight(
        self,
        skill_id: str,
        delta: float,
        tenant_id: str,
        cognitive_trace_id: str,
    ) -> dict:
        """Adjust a skill's importance weight.

        Args:
            skill_id: Target skill identifier.
            delta: Weight adjustment (positive or negative).
            tenant_id: MUST scope to tenant (LAW-6).
            cognitive_trace_id: MUST propagate (LAW-11).

        Returns:
            {"skill_id": str, "new_weight": float, "updated": bool}
        """
        ...
