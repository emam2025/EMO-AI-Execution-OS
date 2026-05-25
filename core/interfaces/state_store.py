"""D8.1 — IExecutionStateStore: persistence + state.

OWNERSHIP: persistence + traces
  - execution state mutation
  - checkpoint save / restore
  - DAG traces
  - event persistence

FORBIDDEN:
  - orchestration
  - dispatch
  - retries
  - scheduling decisions
"""

from typing import Any, Dict, Optional, Protocol

from core.models.dag import DependencyGraph, NodeState, PlanNode


class IExecutionStateStore(Protocol):
    """Owns persistence and execution state — nothing else."""

    def get_state(self, node_id: str) -> Optional[NodeState]:
        """Return current state of a node."""

    def set_state(
        self,
        node: PlanNode,
        state: NodeState,
    ) -> None:
        """Mutate node state. Must validate transitions."""

    def store_trace(
        self,
        session_id: str,
        dag: DependencyGraph,
        node_results: Dict[str, Any],
        status: str,
    ) -> None:
        """Persist a DAG execution trace."""

    def save_checkpoint(
        self,
        execution_id: str,
        dag: DependencyGraph,
        results: Dict[str, Any],
    ) -> None:
        """Save a checkpoint for recovery."""

    def restore_checkpoint(
        self,
        execution_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Restore a previously saved checkpoint."""
