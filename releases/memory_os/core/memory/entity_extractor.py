"""
Entity Extractor — unified interface for entity/relationship extraction.

IEntityExtractor: protocol for extracting entities and relationships from text/traces.
Supports mock (testing) and regex/heuristic (lightweight baseline).
Zero external dependencies.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class EntityType(Enum):
    TOOL = "tool"
    FUNCTION = "function"
    AGENT = "agent"
    ERROR = "error"
    MODULE = "module"
    CONCEPT = "concept"


class EdgeType(Enum):
    CALLS = "calls"
    DEPENDS_ON = "depends_on"
    FAILS_WITH = "fails_with"
    CONTAINS = "contains"
    RELATED_TO = "related_to"


@dataclass(frozen=True)
class Entity:
    entity_id: str
    tenant_id: str
    project_id: str
    name: str
    entity_type: EntityType
    context: str = ""
    source_text: str = ""
    embedding_id: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.project_id:
            raise ValueError("project_id is required")


@dataclass(frozen=True)
class Relationship:
    relationship_id: str
    tenant_id: str
    project_id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.project_id:
            raise ValueError("project_id is required")


@runtime_checkable
class IEntityExtractor(Protocol):
    def extract_entities(self, text: str, tenant_id: str, project_id: str, **kwargs: Any) -> List[Entity]:
        ...
    def map_relationships(self, entities: List[Entity], context: str, tenant_id: str, project_id: str) -> List[Relationship]:
        ...


# ── heuristic patterns ─────────────────────────────────────

_TOOL_PATTERN = re.compile(r"\b(?:tool|api|endpoint|service|module)\s+['\"]?([\w-]+)['\"]?", re.I)
_FUNCTION_PATTERN = re.compile(r"\b(?:function|method|handler|fn)\s+['\"]?(\w+)['\"]?", re.I)
_ERROR_PATTERN = re.compile(r"\b(?:error|exception|fail|crash|bug|issue)\s*[: ](\w+)", re.I)
_AGENT_PATTERN = re.compile(r"\b(?:agent|actor|user|client)\s+['\"]?(\w+)['\"]?", re.I)


class HeuristicEntityExtractor:
    """Lightweight regex-based entity extractor for testing and basic use.

    Detects tools, functions, errors, and agents from plain text.
    """

    def __init__(self, default_entity_type: EntityType = EntityType.CONCEPT):
        self._default_type = default_entity_type

    def extract_entities(
        self,
        text: str,
        tenant_id: str,
        project_id: str,
        **kwargs: Any,
    ) -> List[Entity]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        entities: List[Entity] = []
        seen: set = set()
        patterns = [
            (EntityType.TOOL, _TOOL_PATTERN),
            (EntityType.FUNCTION, _FUNCTION_PATTERN),
            (EntityType.ERROR, _ERROR_PATTERN),
            (EntityType.AGENT, _AGENT_PATTERN),
        ]
        for etype, pat in patterns:
            for match in pat.finditer(text):
                name = match.group(1).lower()
                if name in seen:
                    continue
                seen.add(name)
                entities.append(Entity(
                    entity_id=f"ent-{uuid.uuid4().hex[:12]}",
                    tenant_id=tenant_id,
                    project_id=project_id,
                    name=name,
                    entity_type=etype,
                    context=text[:100],
                    source_text=match.group(0),
                ))
        return entities

    def map_relationships(
        self,
        entities: List[Entity],
        context: str = "",
        tenant_id: str = "",
        project_id: str = "",
    ) -> List[Relationship]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        rels: List[Relationship] = []
        for i, src in enumerate(entities):
            for j, tgt in enumerate(entities):
                if i >= j:
                    continue
                edge = self._infer_edge_type(src.entity_type, tgt.entity_type)
                rels.append(Relationship(
                    relationship_id=f"rel-{uuid.uuid4().hex[:12]}",
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_id=src.entity_id,
                    target_id=tgt.entity_id,
                    edge_type=edge,
                    weight=1.0,
                ))
        return rels

    @staticmethod
    def _infer_edge_type(src_type: EntityType, tgt_type: EntityType) -> EdgeType:
        if src_type == EntityType.TOOL and tgt_type == EntityType.FUNCTION:
            return EdgeType.CALLS
        if src_type == EntityType.ERROR:
            return EdgeType.FAILS_WITH
        if tgt_type == EntityType.ERROR:
            return EdgeType.FAILS_WITH
        if src_type == EntityType.MODULE and tgt_type == EntityType.TOOL:
            return EdgeType.CONTAINS
        return EdgeType.RELATED_TO
