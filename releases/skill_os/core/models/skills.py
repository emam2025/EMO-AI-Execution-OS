"""
Skill OS Data Models — SkillNode, ExecutionBlueprint, SkillEvolutionRecord.

All models enforce:
- LAW-6: tenant_id mandatory on every root model.
- LAW-11: every query must scope by tenant_id.
- tier mandatory: Draft → Verified → Optimized → Deprecated.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SkillTier(str, Enum):
    DRAFT = "draft"
    VERIFIED = "verified"
    OPTIMIZED = "optimized"
    DEPRECATED = "deprecated"

    def __str__(self) -> str:
        return self.value


class SkillDomain(str, Enum):
    CODING = "coding"
    DEBUGGING = "debugging"
    DEPLOYMENT = "deployment"
    PLANNING = "planning"
    COMMUNICATION = "communication"
    UNKNOWN = "unknown"


@dataclass
class SkillNode:
    """Core skill entity stored in the skill graph.

    Immutable after creation except for tier.
    """

    skill_id: str
    tenant_id: str
    project_id: str
    skill_name: str
    pattern_hash: str
    confidence_score: float
    tier: SkillTier = SkillTier.DRAFT
    domain: SkillDomain = SkillDomain.UNKNOWN
    source_trace_ids: List[str] = field(default_factory=list)
    execution_count: int = 0
    success_rate: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.skill_id:
            raise ValueError("skill_id is required")
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError("confidence_score must be in [0.0, 1.0]")

    @staticmethod
    def compute_pattern_hash(pattern: dict) -> str:
        raw = json.dumps(pattern, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass
class ExecutionBlueprint:
    """Reusable execution plan extracted from a skill pattern."""

    blueprint_id: str
    skill_id: str
    tenant_id: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    tool_sequence: List[str] = field(default_factory=list)
    resource_profile: Dict[str, Any] = field(default_factory=dict)
    failure_guardrails: List[str] = field(default_factory=list)
    expected_duration_ms: float = 0.0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.blueprint_id:
            raise ValueError("blueprint_id is required")


@dataclass
class SkillEvolutionRecord:
    """Auditable record of a tier transition."""

    record_id: str
    skill_id: str
    tenant_id: str
    from_tier: SkillTier
    to_tier: SkillTier
    timestamp: float = field(default_factory=time.time)
    reason: str = ""
    validator_signature: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.record_id:
            raise ValueError("record_id is required")


@dataclass
class SkillStoreEntry:
    """Persistence wrapper for a skill in the skill store."""

    entry_id: str
    skill: SkillNode
    blueprints: List[ExecutionBlueprint] = field(default_factory=list)
    evolution_history: List[SkillEvolutionRecord] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    checksum: str = ""

    def __post_init__(self) -> None:
        if not self.entry_id:
            raise ValueError("entry_id is required")
