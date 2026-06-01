"""D8.1 — IExecutionStateStore: persistence + traces.

LAW 26: StateStore owns persistence + traces.
FORBIDDEN: dispatch, retry, lease, scheduling.

Source of Truth: core/runtime/services/state_store.py::ExecutionStateStore

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 26
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable


class PersistenceError(Exception):
    """Raised when state cannot be persisted."""


class LoadError(Exception):
    """Raised when state cannot be read."""


class CheckpointError(Exception):
    """Raised when checkpoint cannot be written."""


class TraceError(Exception):
    """Raised when trace cannot be read."""


@runtime_checkable
class IExecutionStateStore(Protocol):
    """Owns persistence + traces — nothing else.

    Contract methods:
      save_state(node_id, state, session_id?)  → None
      load_state(node_id, session_id?)  → Optional[Any]
      store_checkpoint(session_id, dag, last_node_id, result)  → None
      read_trace(session_id)  → Optional[Dict]
    """

    def save_state(
        self,
        node_id: str,
        state: Any,
        session_id: str = "",
    ) -> None:
        """Persist a node's state."""

    def load_state(
        self,
        node_id: str,
        session_id: str = "",
    ) -> Optional[Any]:
        """Load a node's persisted state."""

    def store_checkpoint(
        self,
        session_id: str,
        dag: Any,
        last_node_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Store an execution checkpoint for resume."""

    def read_trace(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Read the full execution trace for a session."""
