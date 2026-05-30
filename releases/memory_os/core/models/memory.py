"""
Memory OS — Data Models with Tenant Isolation (LAW-6, LAW-11, LAW-14).

Every model enforces mandatory tenant_id, project_id, and cognitive_trace_id.
Zero shared state with R1 — fully isolated data layer.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class MemoryLayer(enum.Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    WORKING = "working"


class PruningPolicy(enum.Enum):
    TTL = "ttl"
    LRU = "lru"
    IMPORTANCE = "importance"
    HYBRID = "hybrid"


class MemoryScope(enum.Enum):
    PROJECT = "project"
    AGENT = "agent"
    GLOBAL = "global"


@dataclass(frozen=True)
class MemoryEntry:
    entry_id: str
    tenant_id: str
    project_id: str
    agent_id: str
    layer: MemoryLayer
    key: str
    content_hash: str
    payload: dict
    scope: MemoryScope = MemoryScope.PROJECT
    ttl_seconds: Optional[int] = None
    importance_weight: float = 1.0
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.agent_id:
            raise ValueError("agent_id is required")


@dataclass(frozen=True)
class ContextWindow:
    window_id: str
    tenant_id: str
    project_id: str
    cognitive_trace_id: str
    trace_id: str
    entries: List[MemoryEntry]
    token_budget: int = 4096
    tokens_used: int = 0
    safety_bounds: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.project_id:
            raise ValueError("project_id is required")


@dataclass(frozen=True)
class ForgettingPolicy:
    policy_id: str
    tenant_id: str
    project_id: str
    cognitive_trace_id: str
    pruning_policy: PruningPolicy
    max_entries: int = 10000
    ttl_default_seconds: int = 86400
    importance_threshold: float = 0.1

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.cognitive_trace_id:
            raise ValueError("cognitive_trace_id is required (LAW-11)")


@dataclass(frozen=True)
class RouterQuery:
    query_id: str = field(default_factory=lambda: f"rq-{uuid.uuid4().hex[:12]}")
    tenant_id: str = ""
    project_id: str = ""
    agent_id: str = ""
    cognitive_trace_id: str = ""
    text: str = ""
    scope: MemoryScope = MemoryScope.PROJECT
    token_budget: int = 1024

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required")


TRACE_PROPAGATION_CHAIN = [
    "EventBus.publish",
    "MemoryRouter.route",
    "IContextCompiler.compress_trace",
    "IContextCompiler.inject_intelligence",
    "IMemoryHierarchy.store",
    "IMemoryHierarchy.retrieve",
    "ISkillGraphManager.record",
    "IMemoryHierarchy.prune",
]
