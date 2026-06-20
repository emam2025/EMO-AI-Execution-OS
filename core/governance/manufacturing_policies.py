"""Manufacturing Policies.

Defines strict governance rules for manufacturing operations.

Ref: RC17.1.1 — Manufacturing Domain Models & Policies
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ManufacturingPolicyType(Enum):
    """Types of manufacturing policies."""

    ISO_9001_QUALITY = "iso_9001_quality"
    OSHA_SAFETY = "osha_safety"
    LINE_SHUTDOWN_APPROVAL = "line_shutdown_approval"


@dataclass(frozen=True)
class ManufacturingPolicy:
    """A manufacturing governance policy rule."""

    policy_type: ManufacturingPolicyType = ManufacturingPolicyType.ISO_9001_QUALITY
    description: str = ""
    action_pattern: str = ""
    requires_approval: bool = False
    severity: str = "medium"
    enabled: bool = True


def get_default_manufacturing_policies() -> List[ManufacturingPolicy]:
    """Return default manufacturing policies.

    These policies enforce:
    - Line shutdown requires approval
    - OSHA safety limits on thermal/mechanical thresholds
    - ISO 9001 quality standards
    """
    return [
        ManufacturingPolicy(
            policy_type=ManufacturingPolicyType.LINE_SHUTDOWN_APPROVAL,
            description="Production line shutdown requires human approval",
            action_pattern="line_shutdown",
            requires_approval=True,
            severity="critical",
        ),
        ManufacturingPolicy(
            policy_type=ManufacturingPolicyType.OSHA_SAFETY,
            description="Thermal threshold exceeded - automatic safety stop required",
            action_pattern="thermal_threshold_exceeded",
            requires_approval=False,
            severity="critical",
        ),
        ManufacturingPolicy(
            policy_type=ManufacturingPolicyType.OSHA_SAFETY,
            description="Mechanical vibration threshold exceeded",
            action_pattern="vibration_threshold_exceeded",
            requires_approval=False,
            severity="high",
        ),
        ManufacturingPolicy(
            policy_type=ManufacturingPolicyType.ISO_9001_QUALITY,
            description="Quality check failure requires rework approval",
            action_pattern="quality_fail",
            requires_approval=True,
            severity="high",
        ),
    ]
