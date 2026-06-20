"""Energy Safety Policy Models — NERC-CIP Compliance.

Pure data structures (stdlib only, zero internal imports).
Defines NERC-CIP policies for energy sector operations.

Ref: RC17.3.2 — Energy Safety Policies
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class EnergyActionType(Enum):
    """Types of energy actions that can be performed."""

    OBSERVE = "observe"                     # Read-only monitoring
    ANALYZE = "analyze"                     # Data analysis
    RECOMMEND = "recommend"                 # Suggestion only
    SIMULATE = "simulate"                   # Simulation run
    CONTROL_WRITE = "control_write"         # Direct control action
    GRID_SHUTDOWN = "grid_shutdown"         # Emergency grid shutdown
    LOAD_SHEDDING = "load_shedding"         # Load shedding
    PLANT_START = "plant_start"             # Plant startup
    PLANT_STOP = "plant_stop"               # Plant shutdown
    MAINTENANCE_EXEC = "maintenance_exec"   # Execute maintenance


class EnergyRiskLevel(Enum):
    """Risk levels for energy operations."""

    LOW = "low"           # Observe, analyze, recommend
    MEDIUM = "medium"     # Simulate
    HIGH = "high"         # Maintenance execution
    CRITICAL = "critical" # Control write, grid shutdown, load shedding


@dataclass(frozen=True)
class NERCCIPPolicy:
    """NERC-CIP policy for energy operations.

    Default Deny: any action not explicitly allowed is denied.
    """

    action_type: EnergyActionType
    requires_approval: bool = False
    min_trust_level: str = "VERIFIED"
    risk_level: EnergyRiskLevel = EnergyRiskLevel.LOW
    description: str = ""


@dataclass(frozen=True)
class EnergySafetyDecision:
    """Result of an energy safety gate evaluation."""

    allowed: bool
    reason: str
    action_type: EnergyActionType
    requires_approval: bool = False
    violation_type: Optional[str] = None


# ── Default NERC-CIP Policies ──────────────────────────────────────────────

DEFAULT_NERC_CIP_POLICIES: Dict[EnergyActionType, NERCCIPPolicy] = {
    EnergyActionType.OBSERVE: NERCCIPPolicy(
        action_type=EnergyActionType.OBSERVE,
        requires_approval=False,
        min_trust_level="UNVERIFIED",
        risk_level=EnergyRiskLevel.LOW,
        description="Read-only monitoring — always allowed",
    ),
    EnergyActionType.ANALYZE: NERCCIPPolicy(
        action_type=EnergyActionType.ANALYZE,
        requires_approval=False,
        min_trust_level="UNVERIFIED",
        risk_level=EnergyRiskLevel.LOW,
        description="Data analysis — always allowed",
    ),
    EnergyActionType.RECOMMEND: NERCCIPPolicy(
        action_type=EnergyActionType.RECOMMEND,
        requires_approval=False,
        min_trust_level="UNVERIFIED",
        risk_level=EnergyRiskLevel.LOW,
        description="Recommendation only — always allowed",
    ),
    EnergyActionType.SIMULATE: NERCCIPPolicy(
        action_type=EnergyActionType.SIMULATE,
        requires_approval=False,
        min_trust_level="VERIFIED",
        risk_level=EnergyRiskLevel.MEDIUM,
        description="Simulation — allowed for verified users",
    ),
    EnergyActionType.CONTROL_WRITE: NERCCIPPolicy(
        action_type=EnergyActionType.CONTROL_WRITE,
        requires_approval=True,
        min_trust_level="TRUSTED",
        risk_level=EnergyRiskLevel.CRITICAL,
        description="Direct control write — requires approval + TRUSTED",
    ),
    EnergyActionType.GRID_SHUTDOWN: NERCCIPPolicy(
        action_type=EnergyActionType.GRID_SHUTDOWN,
        requires_approval=True,
        min_trust_level="TRUSTED",
        risk_level=EnergyRiskLevel.CRITICAL,
        description="Emergency grid shutdown — requires approval + TRUSTED",
    ),
    EnergyActionType.LOAD_SHEDDING: NERCCIPPolicy(
        action_type=EnergyActionType.LOAD_SHEDDING,
        requires_approval=True,
        min_trust_level="TRUSTED",
        risk_level=EnergyRiskLevel.CRITICAL,
        description="Load shedding — requires approval + TRUSTED",
    ),
    EnergyActionType.PLANT_START: NERCCIPPolicy(
        action_type=EnergyActionType.PLANT_START,
        requires_approval=True,
        min_trust_level="TRUSTED",
        risk_level=EnergyRiskLevel.HIGH,
        description="Plant startup — requires approval + TRUSTED",
    ),
    EnergyActionType.PLANT_STOP: NERCCIPPolicy(
        action_type=EnergyActionType.PLANT_STOP,
        requires_approval=True,
        min_trust_level="TRUSTED",
        risk_level=EnergyRiskLevel.HIGH,
        description="Plant shutdown — requires approval + TRUSTED",
    ),
    EnergyActionType.MAINTENANCE_EXEC: NERCCIPPolicy(
        action_type=EnergyActionType.MAINTENANCE_EXEC,
        requires_approval=True,
        min_trust_level="VERIFIED",
        risk_level=EnergyRiskLevel.HIGH,
        description="Execute maintenance — requires approval + VERIFIED",
    ),
}
