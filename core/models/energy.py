"""Energy Sector — Domain Models.

Pure data structures (stdlib only, zero internal imports).
Defines energy-specific assets, policies, and operational models.

Ref: RC17.3 — Energy Pack Foundation
Ref: LAW 6 (Shared Models MUST NOT live inside runtime engines)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ───────────────────────────────────────────────────────────────────


class EnergyAssetType(Enum):
    """Types of energy assets."""

    POWER_PLANT = "power_plant"
    GRID_NODE = "grid_node"
    SMART_METER = "smart_meter"
    SUBSTATION = "substation"
    TRANSMISSION_LINE = "transmission_line"
    DISTRIBUTION_PANEL = "distribution_panel"
    RENEWABLE_SOURCE = "renewable_source"
    BATTERY_STORAGE = "battery_storage"


class PlantType(Enum):
    """Types of power plants."""

    THERMAL = "thermal"
    NUCLEAR = "nuclear"
    HYDRO = "hydro"
    SOLAR = "solar"
    WIND = "wind"
    GAS_TURBINE = "gas_turbine"
    COMBINED_CYCLE = "combined_cycle"


class GridNodeType(Enum):
    """Types of grid nodes."""

    GENERATION = "generation"
    TRANSMISSION = "transmission"
    DISTRIBUTION = "distribution"
    CONSUMER = "consumer"


class EnergyEventSeverity(Enum):
    """Severity levels for energy operational events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MaintenanceStatus(Enum):
    """Maintenance ticket status."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MaintenancePriority(Enum):
    """Maintenance priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PowerPlant:
    """Represents a power generation plant."""

    id: str
    name: str
    plant_type: PlantType
    capacity_mw: float
    current_output_mw: float = 0.0
    efficiency_pct: float = 0.0
    status: str = "operational"  # operational, maintenance, offline
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class GridNode:
    """Represents a node in the power grid."""

    id: str
    name: str
    node_type: GridNodeType
    voltage_kv: float = 0.0
    current_load_mw: float = 0.0
    max_capacity_mw: float = 0.0
    status: str = "active"  # active, inactive, faulted
    connected_nodes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class SmartMeter:
    """Represents a smart meter for energy consumption monitoring."""

    id: str
    name: str
    location: str
    current_draw_kw: float = 0.0
    daily_consumption_kwh: float = 0.0
    peak_demand_kw: float = 0.0
    meter_status: str = "active"  # active, inactive, tampered
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class LoadProfile:
    """Represents a load profile for demand forecasting."""

    id: str
    name: str
    hourly_loads_kw: List[float] = field(default_factory=list)
    peak_load_kw: float = 0.0
    average_load_kw: float = 0.0
    factor: float = 0.0  # peak / average
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class MaintenanceTicket:
    """Represents a maintenance ticket for energy assets."""

    id: str
    asset_id: str
    title: str
    description: str
    priority: MaintenancePriority = MaintenancePriority.MEDIUM
    status: MaintenanceStatus = MaintenanceStatus.OPEN
    assigned_to: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EnergyOperationalEvent:
    """Represents an operational event in the energy domain."""

    id: str
    asset_id: str
    event_type: str
    severity: EnergyEventSeverity
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnergyTwinState:
    """Represents the current state of an energy digital twin."""

    asset_id: str
    state: Dict[str, Any] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
