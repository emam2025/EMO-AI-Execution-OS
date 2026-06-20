"""Manufacturing Domain Models.

Pure data structures using stdlib only. Zero internal imports.

Ref: RC17.1.1 — Manufacturing Domain Models & Policies
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


class LineStatus(Enum):
    """Production line operational status."""

    RUNNING = "running"
    STOPPED = "stopped"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"


class VehicleStatus(Enum):
    """Fleet vehicle status."""

    ACTIVE = "active"
    IN_TRANSIT = "in_transit"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class WorkOrderStatus(Enum):
    """Maintenance work order status."""

    PENDING = "pending"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class QualityResult(Enum):
    """Quality check result."""

    PASS = "pass"
    FAIL = "fail"
    CONDITIONAL = "conditional"


class RouteStatus(Enum):
    """Supply route status."""

    ACTIVE = "active"
    DELAYED = "delayed"
    BLOCKED = "blocked"
    CLOSED = "closed"


@dataclass(frozen=True)
class ProductionLine:
    """Represents a manufacturing production line."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    status: LineStatus = LineStatus.RUNNING
    current_throughput: float = 0.0
    max_capacity: float = 100.0
    twin_asset_id: Optional[str] = None


@dataclass(frozen=True)
class Warehouse:
    """Represents a warehouse storage facility."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    location: str = ""
    capacity: float = 1000.0
    current_inventory_level: float = 0.0


@dataclass(frozen=True)
class FleetVehicle:
    """Represents a vehicle in the fleet."""

    id: str = field(default_factory=lambda: str(uuid4()))
    type: str = ""
    status: VehicleStatus = VehicleStatus.ACTIVE
    current_location: str = ""
    maintenance_due_date: Optional[datetime] = None


@dataclass(frozen=True)
class MaintenanceWorkOrder:
    """Represents a maintenance work order."""

    id: str = field(default_factory=lambda: str(uuid4()))
    asset_id: str = ""
    priority: str = "medium"
    status: WorkOrderStatus = WorkOrderStatus.PENDING
    requested_by: str = ""
    approved_by: Optional[str] = None


@dataclass(frozen=True)
class QualityCheck:
    """Represents a quality check result."""

    id: str = field(default_factory=lambda: str(uuid4()))
    production_line_id: str = ""
    result: QualityResult = QualityResult.PASS
    defects_found: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class SupplyRoute:
    """Represents a supply chain route."""

    id: str = field(default_factory=lambda: str(uuid4()))
    origin: str = ""
    destination: str = ""
    estimated_time: float = 0.0
    status: RouteStatus = RouteStatus.ACTIVE
