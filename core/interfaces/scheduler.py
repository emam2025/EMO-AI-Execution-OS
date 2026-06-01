"""D8.1 — IExecutionScheduler: execution ordering only.

LAW 23: Scheduler owns execution ordering.
FORBIDDEN: retry, dispatch, lease, state.

Source of Truth: core/runtime/services/scheduler.py::ExecutionScheduler

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 23
"""

from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


class SchedulingError(Exception):
    """Raised when DAG scheduling fails (cycles, invalid deps)."""


class CollectError(Exception):
    """Raised when future collection encounters unhandled errors."""


@runtime_checkable
class IExecutionScheduler(Protocol):
    """Owns execution ordering — nothing else.

    Contract methods:
      schedule(dag, session_id?, strategy?)  → levels
      run_with_timeout(node, runner, timeout) → result
      collect_futures(futures, session_id?)  → results
    """

    def schedule(
        self,
        dag: Any,
        session_id: Optional[str] = None,
        strategy: str = "balanced",
    ) -> List[List[Any]]:
        """Partition DAG nodes into execution levels.
        Returns levels of parallel-executable nodes.
        """

    def run_with_timeout(
        self,
        node: Any,
        runner: Callable[..., Any],
        timeout: float = 30.0,
    ) -> Any:
        """Execute a single node with timeout enforcement."""

    def collect_futures(
        self,
        futures: Dict[Any, Any],
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Collect and process completed futures from a level."""
