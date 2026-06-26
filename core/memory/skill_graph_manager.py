"""SkillGraphManager — concrete implementation of ISkillGraphManager.

LAW 6: SkillNode model defined outside runtime.
LAW 8: Every mutation is recoverable via cognitive_trace_id.
RULE 1: Skill graph uses its own layer (PROCEDURAL) — no cross-layer imports.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from core.memory.models import (  # LAW-6
    SkillNode,
    FailurePattern,
)


class SkillGraphManager:  # LAW-6 LAW-8 RULE-1
    """Governs the Procedural memory layer — tool chains, plans, patterns."""

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._skills: Dict[str, SkillNode] = {}  # skill_id → SkillNode
        self._failure_patterns: Dict[str, FailurePattern] = {}

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
        skill_id = f"skill_{uuid.uuid4().hex[:12]}"
        node = SkillNode(
            skill_id=skill_id,
            intent_pattern=intent,
            dag_template_hash=plan_hash,
            tool_chain=tool_chain,
            cost_profile={"total": Decimal(str(cost_units))},
            tenant_id=tenant_id,
            cognitive_trace_id=cognitive_trace_id,
        )
        self._skills[skill_id] = node

        if self._db is not None:
            await self._db.save_skill_node(
                id=skill_id,
                skill_id=skill_id,
                intent_pattern=intent,
                dag_template_hash=plan_hash,
                tool_chain=json.dumps(tool_chain, default=str),
                cost_profile=json.dumps({k: str(v) for k, v in node.cost_profile.items()}),
                tenant_id=tenant_id,
                cognitive_trace_id=cognitive_trace_id,
                success_rate=float(node.success_rate),
                prerequisites=json.dumps(node.prerequisites),
            )

        return {
            "status": "recorded",
            "skill_id": skill_id,
            "cognitive_trace_id": cognitive_trace_id,
        }

    async def retrieve_skill(
        self,
        query_intent: str,
        tenant_id: str,
        top_k: int = 3,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        matched: List[Dict[str, Any]] = []
        for skill_id, node in self._skills.items():
            if node.tenant_id != tenant_id:
                continue  # LAW-11: strict tenant isolation
            score = self._match_intent(query_intent, node.intent_pattern)
            matched.append({
                "skill_id": skill_id,
                "intent_pattern": node.intent_pattern,
                "dag_template_hash": node.dag_template_hash,
                "success_rate": node.success_rate,
                "cost_profile": {k: str(v) for k, v in node.cost_profile.items()},
                "prerequisites": node.prerequisites,
                "match_score": score,
            })
        matched.sort(key=lambda x: x["match_score"], reverse=True)
        matched = matched[:top_k]
        return {
            "status": "ok",
            "skills": matched,
            "total": len(matched),
            "cognitive_trace_id": cognitive_trace_id,
        }

    async def update_procedural_weight(
        self,
        skill_id: str,
        feedback: float,
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        node = self._skills.get(skill_id)
        if node is None:
            return {"status": "error", "message": f"Skill {skill_id} not found",
                    "cognitive_trace_id": cognitive_trace_id}
        if node.tenant_id != tenant_id:
            return {"status": "error", "message": "Tenant mismatch",
                    "cognitive_trace_id": cognitive_trace_id}  # LAW-11

        node.success_rate = max(0.0, min(1.0, node.success_rate + feedback * 0.1))

        if self._db is not None:
            await self._db.update_skill_node_success_rate(skill_id, node.success_rate)

        return {
            "status": "updated",
            "skill_id": skill_id,
            "new_success_rate": round(node.success_rate, 4),
            "cognitive_trace_id": cognitive_trace_id,
        }

    async def record_failure_pattern(
        self,
        dag_id: str,
        failure_hash: str,
        tenant_id: str,
        failure_signal: str,
        tool_chain: List[Dict[str, Any]],
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        pattern_id = f"fail_{uuid.uuid4().hex[:12]}"
        pattern = FailurePattern(
            pattern_id=pattern_id,
            dag_id=dag_id,
            failure_hash=failure_hash,
            failure_signal=failure_signal,
            tool_chain_at_failure=tool_chain,
            tenant_id=tenant_id,
            cognitive_trace_id=cognitive_trace_id,
        )
        self._failure_patterns[pattern_id] = pattern

        if self._db is not None:
            await self._db.save_failure_pattern(
                id=pattern_id,
                pattern_id=pattern_id,
                dag_id=dag_id,
                failure_hash=failure_hash,
                failure_signal=failure_signal,
                tool_chain_at_failure=json.dumps(tool_chain, default=str),
                tenant_id=tenant_id,
                cognitive_trace_id=cognitive_trace_id,
            )

        return {
            "status": "recorded",
            "pattern_id": pattern_id,
            "cognitive_trace_id": cognitive_trace_id,
        }

    @staticmethod
    def _match_intent(query: str, pattern: str) -> float:
        q = query.lower().strip()
        p = pattern.lower().strip()
        if q == p:
            return 1.0
        q_words = set(q.split())
        p_words = set(p.split())
        if not q_words or not p_words:
            return 0.0
        intersection = q_words & p_words
        return round(len(intersection) / max(len(q_words), len(p_words)), 4)
