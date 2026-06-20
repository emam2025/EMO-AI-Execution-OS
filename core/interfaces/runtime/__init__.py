"""Runtime Interfaces — Compatibility Layer.

This module provides a single import point for both:
- Protocol interfaces (IExecutionScheduler, etc.)
- Concrete implementations (ExecutionScheduler, etc.)

Source of Truth:
- Protocols: core/interfaces/*.py
- Implementations: core/runtime/services/*.py

This layer does NOT modify runtime behavior.
It only re-exports for developer convenience.
"""

from __future__ import annotations

# ── Protocol Interfaces (Contracts) ────────────────────────
from core.interfaces.scheduler import IExecutionScheduler
from core.interfaces.state_store import IExecutionStateStore
from core.interfaces.dispatcher import IExecutionDispatcher
from core.interfaces.retry import IExecutionRetryHandler
from core.interfaces.lease import IExecutionLeaseManager

# ── Concrete Implementations (Re-exports) ──────────────────
# These are re-exported from core/runtime/services/ for convenience.
# The Source of Truth remains in core/runtime/services/.
from core.runtime.services.scheduler import ExecutionScheduler
from core.runtime.services.state_store import ExecutionStateStore
from core.runtime.services.tool_dispatcher import ExecutionToolDispatcher
from core.runtime.services.retry_handler import ExecutionRetryHandler
from core.runtime.services.lease_manager import ExecutionLeaseManager

__all__ = [
    # Protocols
    "IExecutionScheduler",
    "IExecutionStateStore",
    "IExecutionDispatcher",
    "IExecutionRetryHandler",
    "IExecutionLeaseManager",
    # Implementations
    "ExecutionScheduler",
    "ExecutionStateStore",
    "ExecutionToolDispatcher",
    "ExecutionRetryHandler",
    "ExecutionLeaseManager",
]
