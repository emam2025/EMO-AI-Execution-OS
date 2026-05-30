"""
R2/R3 Read-Only Bridges — isolated contracts with zero mutation.

Fetches memory context from R2 (Memory OS) and skill patterns from R3
(Skill OS) without direct imports, execution, or modification.
LAW-6 enforced on all public methods.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List


class R2MemoryBridge:
    """Read-only bridge to Memory OS (R2) context.

    No imports from releases/memory_os/.
    Zero mutation — getters only.
    """

    _mock_store: Dict[str, Dict[str, Any]] = {}

    def fetch_memory_context(
        self,
        trace_id: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not trace_id:
            raise ValueError("trace_id is required")
        key = f"{tenant_id}:{trace_id}"
        if key in self._mock_store:
            ctx = dict(self._mock_store[key])
            ctx["_read_only"] = True
            return ctx
        return {
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "context": "cognitive_request",
            "timestamp": time.time(),
            "_read_only": True,
            "_source": "r2_memory_bridge",
        }

    def list_project_traces(
        self,
        tenant_id: str,
        project_id: str,
    ) -> List[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not project_id:
            raise ValueError("project_id is required")
        return [
            {
                "trace_id": f"trace-{uuid.uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "project_id": project_id,
                "timestamp": time.time(),
                "_read_only": True,
                "_source": "r2_memory_bridge",
            }
        ]

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            raise AttributeError(
                f"R2MemoryBridge is read-only; cannot set attribute '{name}'"
            )


class R3SkillBridge:
    """Read-only bridge to Skill OS (R3) patterns.

    No imports from releases/skill_os/.
    Zero mutation — getters only.
    """

    _mock_patterns: Dict[str, List[Dict[str, Any]]] = {}

    def fetch_skill_patterns(
        self,
        domain: str,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not domain:
            raise ValueError("domain is required")
        patterns = self._mock_patterns.get(domain, [])
        if patterns:
            results = []
            for p in patterns:
                if p.get("tenant_id") in (tenant_id, "", "*"):
                    result = dict(p)
                    result["_read_only"] = True
                    results.append(result)
            return results
        return [
            {
                "pattern_id": f"pat-{uuid.uuid4().hex[:12]}",
                "domain": domain,
                "tenant_id": tenant_id,
                "name": f"{domain}_extractor",
                "version": "1.0.0",
                "tier": "verified",
                "_read_only": True,
                "_source": "r3_skill_bridge",
            },
        ]

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            raise AttributeError(
                f"R3SkillBridge is read-only; cannot set attribute '{name}'"
            )


def fetch_memory_context(
    trace_id: str,
    tenant_id: str,
) -> Dict[str, Any]:
    return R2MemoryBridge().fetch_memory_context(trace_id, tenant_id)


def fetch_skill_patterns(
    domain: str,
    tenant_id: str,
) -> List[Dict[str, Any]]:
    return R3SkillBridge().fetch_skill_patterns(domain, tenant_id)
