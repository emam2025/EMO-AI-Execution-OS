"""Water Sector — Domain Models.

Pure data structures (stdlib only, zero internal imports).
Defines water-specific assets, actions, and safety models.

Ref: RC17.4 — Water Pack Foundation
Ref: LAW 6 (Shared Models MUST NOT live inside runtime engines)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ───────────────────────────────────────────────────────────────────


class WaterAssetType(Enum):
    """Types of water infrastructure assets."""

    TREATMENT_PLANT = "treatment_plant"
    PUMP_STATION = "pump_station"
    WATER_QUALITY_SENSOR = "water_quality_sensor"
    RESERVOIR = "reservoir"
    PIPELINE = "pipeline"
    VALVE = "valve"


class WaterActionType(Enum):
    """Action types for water operations."""

    OBSERVE = "observe"
    ANALYZE = "analyze"
    RECOMMEND = "recommend"
    CONTROL_WRITE = "control_write"
    PUMP_SHUTDOWN = "pump_shutdown"
    VALVE_OVERRIDE = "valve_override"


class WaterPolicyType(Enum):
    """Policy types for water governance."""

    WHO_QUALITY_STANDARD = "who_quality_standard"
    EPA_COMPLIANCE = "epa_compliance"
    CONTROL_WRITE_DENY = "control_write_deny"


class WaterEventSeverity(Enum):
    """Severity levels for water operational events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TreatmentPlant:
    """Represents a water treatment plant."""

    asset_id: str
    name: str
    capacity_mld: float = 0.0
    current_flow_mld: float = 0.0
    status: str = "operational"
    twin_asset_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class PumpStation:
    """Represents a water pump station."""

    asset_id: str
    name: str
    pump_count: int = 0
    active_pumps: int = 0
    status: str = "operational"
    twin_asset_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class WaterQualitySensor:
    """Represents a water quality sensor."""

    asset_id: str
    location: str
    ph_level: float = 7.0
    turbidity_ntu: float = 0.0
    chlorine_ppm: float = 0.0
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class WaterSafetyDecision:
    """Decision returned by WaterSafetyGate evaluation."""

    allowed: bool
    reason: str
    action_type: WaterActionType
    requires_approval: bool = False
    violation_type: Optional[str] = None


@dataclass
class WaterTwinState:
    """Mutable digital twin state for a water asset."""

    asset_id: str
    state: Dict[str, Any] = field(default_factory=dict)
    version: int = 0
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class WaterOperationalEvent:
    """An operational event recorded by the water twin."""

    event_id: str
    asset_id: str
    event_type: str
    severity: WaterEventSeverity
    message: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)
