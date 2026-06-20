"""Pilot Guardrails Configuration.

Production-ready thresholds, safety limits, approval rules, and rollback rules
for the industrial Pilot deployment.

Ref: Pilot.1.3 — Pilot APIs Documentation & Guardrails Configuration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class OEEThresholds:
    """OEE alert thresholds — triggered when overall OEE drops below threshold."""

    overall_oee_pct: float = 60.0
    availability_pct: float = 70.0
    performance_pct: float = 75.0
    quality_pct: float = 95.0


@dataclass(frozen=True)
class SafetyLimits:
    """Critical safety limits — exceeding these triggers immediate safety violation."""

    temperature_max_celsius: float = 95.0
    vibration_max: float = 5.0
    pressure_max_psi: float = 150.0
    runtime_max_seconds: float = 3600.0


@dataclass(frozen=True)
class ApprovalRules:
    """Actions requiring mandatory human-in-the-loop approval."""

    actions: tuple = (
        "line_shutdown",
        "emergency_stop",
        "quarantine_batch",
        "approve_work_order",
        "reorder_stock",
        "dispatch_vehicle",
        "override_route",
    )
    required_autonomy_level: str = "L2"
    timeout_seconds: int = 300


@dataclass(frozen=True)
class RollbackRules:
    """Auto-rollback rules on repeated failures."""

    max_consecutive_failures: int = 3
    rollback_scope: str = "agent"
    cooldown_seconds: int = 60
    escalation_threshold: int = 5


# --- Singleton Instances ---

PILOT_OEE_THRESHOLDS = OEEThresholds()
PILOT_SAFETY_LIMITS = SafetyLimits()
PILOT_APPROVAL_RULES = ApprovalRules()
PILOT_ROLLBACK_RULES = RollbackRules()
