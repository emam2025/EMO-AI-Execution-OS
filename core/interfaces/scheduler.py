"""D8.1 — IExecutionScheduler: execution ordering only.

OWNERSHIP: execution ordering
  - level ordering / dispatch timing
  - queue ordering
  - worker allocation decisions

FORBIDDEN:
  - state mutation
  - retry logic
  - lease ownership
  - tool dispatch execution
"""

from typing import Any, Dict, List, Optional, Protocol

from core.models.dag import DependencyGraph, PlanNode


class IExecutionScheduler(Protocol):
    """Owns execution ordering — nothing else."""

    def order_levels(self, dag: DependencyGraph) -> List[List[PlanNode]]:
        """Return topologically sorted independent levels."""

    def select_ready_nodes(
        self,
        dag: DependencyGraph,
        in_progress: set[str],
        completed: set[str],
    ) -> List[PlanNode]:
        """Return nodes whose dependencies are satisfied and not in progress."""

    def allocate_worker(
        self,
        node: PlanNode,
        pool_size: int,
        active_count: int,
    ) -> int:
        """Decide worker pool slot allocation for a node."""

    def estimate_execution_order(
        self,
        dag: DependencyGraph,
        strategy: str,
    ) -> list[str]:
        """Return node IDs in estimated execution order for the given strategy."""
