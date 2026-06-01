"""D8 Service Mesh — Runtime Protocol Interfaces.

Re-exports all 5 service protocols + failure propagation
from the canonical interface definitions.
"""

from core.interfaces.scheduler import IExecutionScheduler
from core.interfaces.state_store import IExecutionStateStore
from core.interfaces.dispatcher import IExecutionDispatcher
from core.interfaces.retry import IExecutionRetryHandler
from core.interfaces.lease import IExecutionLeaseManager
from core.interfaces.failure_propagation import (
    FailureDomain,
    FailurePropagationPolicy,
    PropagationAction,
    DegradeMode,
    PropagationRule,
    PROPAGATION_MATRIX,
)

__all__ = [
    "IExecutionScheduler",
    "IExecutionStateStore",
    "IExecutionDispatcher",
    "IExecutionRetryHandler",
    "IExecutionLeaseManager",
    "FailureDomain",
    "FailurePropagationPolicy",
    "PropagationAction",
    "DegradeMode",
    "PropagationRule",
    "PROPAGATION_MATRIX",
]
