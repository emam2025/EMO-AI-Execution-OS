"""D8.1 — ExecutionStateStore: persistence + traces (LAW 26).

LAW 26: StateStore owns persistence + traces.
FORBIDDEN: dispatch, retry, lease, scheduling.

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 26
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("emo_ai.services.state_store")


class PersistenceError(Exception):
    """Raised when state cannot be persisted."""


class LoadError(Exception):
    """Raised when state cannot be read."""


class CheckpointError(Exception):
    """Raised when checkpoint cannot be written."""


class TraceError(Exception):
    """Raised when trace cannot be read."""


class ExecutionStateStore:
    """Persistence + traces service — owns state, cache, checkpoints, traces.

    LAW 26: StateStore owns persistence + traces.
    Private state: _cache, _checkpoints, _traces.
    No access to dispatcher, retry_handler, scheduler, or lease_manager state.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 26
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}
        self._checkpoints: Dict[str, Dict[str, Any]] = {}
        self._traces: Dict[str, Dict[str, Any]] = {}

    def save_state(
        self,
        node_id: str,
        state: Any,
        session_id: str = "",
    ) -> None:
        """Persist a node's state.

        LAW 26: Only StateStore may persist node states.
        Saves to in-memory cache keyed by node_id.

        Args:
            node_id: Unique node identifier.
            state: Node state value to persist.
            session_id: Session identifier for trace grouping.

        Raises:
            PersistenceError: If state cannot be written.
        """
        try:
            key = f"{session_id}:{node_id}" if session_id else node_id
            serializable = self._make_serializable(state)
            self._cache[key] = serializable

            # Update trace if session_id provided
            if session_id:
                if session_id not in self._traces:
                    self._traces[session_id] = {
                        "session_id": session_id,
                        "nodes": {},
                        "started_at": time.time(),
                    }
                self._traces[session_id]["nodes"][node_id] = {
                    "state": serializable,
                    "timestamp": time.time(),
                }

            logger.debug("State saved for %s (session=%s)", node_id, session_id)
        except Exception as e:
            raise PersistenceError(
                f"Cannot persist state for node {node_id}: {e}"
            ) from e

    def load_state(
        self,
        node_id: str,
        session_id: str = "",
    ) -> Optional[Any]:
        """Load a node's persisted state.

        Args:
            node_id: Unique node identifier.
            session_id: Session identifier.

        Returns:
            The persisted state, or None if not found.

        Raises:
            LoadError: If state cannot be read.
        """
        try:
            key = f"{session_id}:{node_id}" if session_id else node_id
            return self._cache.get(key)
        except Exception as e:
            raise LoadError(
                f"Cannot load state for node {node_id}: {e}"
            ) from e

    def store_checkpoint(
        self,
        session_id: str,
        dag: Any,
        last_node_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Store an execution checkpoint for resume.

        Args:
            session_id: Session identifier.
            dag: Current DependencyGraph state.
            last_node_id: ID of the last completed node.
            result: Execution result of the last node.

        Raises:
            CheckpointError: If checkpoint cannot be written.
        """
        try:
            self._checkpoints[session_id] = {
                "session_id": session_id,
                "dag": self._make_serializable(dag),
                "last_node_id": last_node_id,
                "result": self._make_serializable(result),
                "timestamp": time.time(),
            }
            logger.debug("Checkpoint stored for session %s", session_id)
        except Exception as e:
            raise CheckpointError(
                f"Cannot write checkpoint for session {session_id}: {e}"
            ) from e

    def read_trace(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Read the full execution trace for a session.

        Args:
            session_id: Session identifier.

        Returns:
            Execution trace dict, or None if no trace exists.

        Raises:
            TraceError: If trace cannot be read.
        """
        try:
            return self._traces.get(session_id)
        except Exception as e:
            raise TraceError(
                f"Cannot read trace for session {session_id}: {e}"
            ) from e

    @staticmethod
    def _make_serializable(obj: Any) -> Any:
        """Convert an object to a JSON-serializable form."""
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [ExecutionStateStore._make_serializable(item) for item in obj]
        if isinstance(obj, dict):
            return {
                str(k): ExecutionStateStore._make_serializable(v)
                for k, v in obj.items()
            }
        if hasattr(obj, "__dict__"):
            return {
                k: ExecutionStateStore._make_serializable(v)
                for k, v in obj.__dict__.items()
                if not k.startswith("_")
            }
        return str(obj)
