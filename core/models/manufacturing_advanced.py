"""Manufacturing Advanced Domain Models.

Pure data structures using stdlib only. Zero internal imports.
Frozen dataclasses for OEE metrics and predictive maintenance alerts.

Ref: RC17.2.1 — OEE Metrics Engine & Predictive Domain Models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class FailureMode(Enum):
    """Predictive maintenance failure modes."""

    OVERHEAT = "overheat"
    VIBRATION = "vibration"
    WEAR = "wear"


@dataclass(frozen=True)
class OEEState:
    """Overall Equipment Effectiveness state for an asset.

    OEE = Availability × Performance × Quality
    """

    asset_id: str = ""
    availability_pct: float = 0.0
    performance_pct: float = 0.0
    quality_pct: float = 0.0
    overall_oee_pct: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class PredictiveAlert:
    """Predictive maintenance alert for an asset."""

    alert_id: str = field(default_factory=lambda: str(uuid4()))
    asset_id: str = ""
    failure_mode: FailureMode = FailureMode.OVERHEAT
    confidence_score: float = 0.0
    estimated_time_to_failure_hours: float = 0.0
    recommended_action: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
