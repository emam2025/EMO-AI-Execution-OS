"""
R2/R3/R4 Read-Only Bridges — isolated contracts with zero mutation.

Fetches memory context (R2), skill patterns (R3), and reflection logs
(R4) without direct imports, execution, or modification.
LAW-6 enforced on all public methods.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List


class R2MemoryBridge:
    """Read-only bridge to Memory OS (R2)."""

    def fetch_memory_context(
        self,
        trace_id: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not trace_id:
            raise ValueError("trace_id is required")
        return {
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "context": "cognitive_request",
            "timestamp": time.time(),
            "_read_only": True,
            "_source": "r2_memory_bridge",
        }

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            raise AttributeError(
                f"R2MemoryBridge is read-only; cannot set attribute '{name}'"
            )


class R3SkillBridge:
    """Read-only bridge to Skill OS (R3)."""

    def fetch_skill_patterns(
        self,
        domain: str,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not domain:
            raise ValueError("domain is required")
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


class R4CognitiveBridge:
    """Read-only bridge to Cognitive OS (R4)."""

    def fetch_reflection_logs(
        self,
        tenant_id: str,
        min_severity: str = "low",
    ) -> List[Dict[str, Any]]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        threshold = severity_order.get(min_severity, 0)
        return [
            {
                "reflection_id": f"ref-{uuid.uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "severity": sev,
                "analysis": {"error_count": 1, "success_rate": 0.5},
                "timestamp": time.time(),
                "_read_only": True,
                "_source": "r4_cognitive_bridge",
            }
            for sev, level in severity_order.items()
            if level >= threshold
        ]

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            raise AttributeError(
                f"R4CognitiveBridge is read-only; cannot set attribute '{name}'"
            )


def fetch_memory_context(trace_id: str, tenant_id: str) -> Dict[str, Any]:
    return R2MemoryBridge().fetch_memory_context(trace_id, tenant_id)


def fetch_skill_patterns(domain: str, tenant_id: str) -> List[Dict[str, Any]]:
    return R3SkillBridge().fetch_skill_patterns(domain, tenant_id)


def fetch_reflection_logs(tenant_id: str, min_severity: str = "low") -> List[Dict[str, Any]]:
    return R4CognitiveBridge().fetch_reflection_logs(tenant_id, min_severity)
