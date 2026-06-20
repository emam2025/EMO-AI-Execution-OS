"""Guardrails Domain Models.

Pure data structures using stdlib only. Zero internal imports.

Ref: P8.2 — Guardrails Engine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


class DriftType(Enum):
    """Types of drift detected by guardrails."""

    BEHAVIORAL_DRIFT = "behavioral_drift"
    PERFORMANCE_REGRESSION = "performance_regression"
    POLICY_VIOLATION = "policy_violation"


class Severity(Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class GuardrailAlert:
    """Alert generated when a drift or regression is detected."""

    alert_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: str = ""
    drift_type: DriftType = DriftType.BEHAVIORAL_DRIFT
    severity: Severity = Severity.MEDIUM
    details: Dict[str, Any] = field(default_factory=dict)
    action_taken: str = ""
