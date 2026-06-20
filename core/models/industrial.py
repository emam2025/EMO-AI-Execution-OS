"""Industrial Intelligence Fabric — Domain Models.

Pure data structures (stdlib only, zero internal imports).

Ref: LAW 6 (Shared Models MUST NOT live inside runtime engines)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ───────────────────────────────────────────────────────────────────


class AssetType(Enum):
    """Types of industrial assets."""

    ORGANIZATION = "organization"
    PLANT = "plant"
    LINE = "production_line"
    MACHINE = "machine"
    SENSOR = "sensor"
    ACTUATOR = "actuator"


class RelationshipType(Enum):
    """Types of relationships between assets."""

    CONTAINS = "contains"           # parent → child
    DEPENDS_ON = "depends_on"       # dependency
    CONNECTS_TO = "connects_to"     # physical connection
    MONITORS = "monitors"           # sensor → machine


class EventSeverity(Enum):
    """Severity levels for operational events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass
class IndustrialAsset:
    """Represents an industrial asset (machine, sensor, plant, etc.)."""

    id: str
    name: str
    asset_type: AssetType
    tenant_id: str
    org_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "active"  # active, inactive, maintenance


@dataclass
class AssetRelationship:
    """Represents a relationship between two assets."""

    id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AssetHierarchy:
    """Hierarchical structure of assets."""

    root_id: str
    assets: List[IndustrialAsset] = field(default_factory=list)
    relationships: List[AssetRelationship] = field(default_factory=list)
    depth: int = 0


@dataclass
class OperationalEvent:
    """Represents an operational event (sensor reading, alarm, etc.)."""

    id: str
    asset_id: str
    event_type: str
    severity: EventSeverity
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TwinState:
    """Represents the current state of a digital twin."""

    asset_id: str
    state: Dict[str, Any] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
