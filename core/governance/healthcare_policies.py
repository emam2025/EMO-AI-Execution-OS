from enum import Enum
from typing import Dict, Any
from core.models.healthcare import HealthcareActionType, HealthcareSafetyDecision


class HealthcarePolicyType(Enum):
    HIPAA_DATA_PRIVACY = "hipaa_data_privacy"
    FDA_DEVICE_SAFETY = "fda_device_safety"
    CONTROL_WRITE_DENY = "control_write_deny"


CONTROL_WRITE_ACTIONS = {
    HealthcareActionType.CONTROL_WRITE,
    HealthcareActionType.PATIENT_DATA_EXPORT,
    HealthcareActionType.DEVICE_RECONFIGURATION,
}


def evaluate_policy(action_type: HealthcareActionType, trust_level: str = "UNTRUSTED") -> HealthcareSafetyDecision:
    if action_type in CONTROL_WRITE_ACTIONS:
        if trust_level != "TRUSTED":
            return HealthcareSafetyDecision(
                allowed=False,
                reason=f"Action {action_type.value} requires TRUSTED approval level",
                action_type=action_type,
                requires_approval=True,
                violation_type="UNAUTHORIZED_CONTROL_WRITE"
            )
        return HealthcareSafetyDecision(
            allowed=True,
            reason=f"Action {action_type.value} approved with TRUSTED level",
            action_type=action_type,
            requires_approval=True,
            violation_type=None
        )
    
    return HealthcareSafetyDecision(
        allowed=True,
        reason=f"Action {action_type.value} allowed by default",
        action_type=action_type,
        requires_approval=False,
        violation_type=None
    )


DEFAULT_HEALTHCARE_POLICIES: Dict[HealthcarePolicyType, Dict[str, Any]] = {
    HealthcarePolicyType.HIPAA_DATA_PRIVACY: {
        "default_deny": [HealthcareActionType.PATIENT_DATA_EXPORT],
        "requires_approval": True,
        "min_trust_level": "TRUSTED",
    },
    HealthcarePolicyType.FDA_DEVICE_SAFETY: {
        "default_deny": [HealthcareActionType.DEVICE_RECONFIGURATION],
        "requires_approval": True,
        "min_trust_level": "TRUSTED",
    },
    HealthcarePolicyType.CONTROL_WRITE_DENY: {
        "default_deny": [HealthcareActionType.CONTROL_WRITE],
        "requires_approval": True,
        "min_trust_level": "TRUSTED",
    },
}