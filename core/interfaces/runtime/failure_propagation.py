"""Re-export: FailureMatrix and backward-compat enums."""
from core.interfaces.failure_propagation import (  # noqa: F401
    FailureDomain, FailureEvent, FailureMatrix, FailureMode,
    FailurePropagationPolicy, PropagationAction, DegradeMode,
    PropagationRule, PROPAGATION_MATRIX,
)
