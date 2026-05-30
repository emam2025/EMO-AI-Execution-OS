"""D8.1 — ExecutionScheduler: execution ordering (LAW 23).

LAW 23: Scheduler owns execution ordering.
FORBIDDEN: retry, dispatch, lease, state.

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 23
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("emo_ai.services.scheduler")


class SchedulingError(Exception):
    """Raised when DAG scheduling fails (cycles, invalid deps)."""


class CollectError(Exception):
    """Raised when future collection encounters unhandled errors."""


class ExecutionScheduler:
    """Execution ordering service — owns schedule, concurrency, level dispatch.

    LAW 23: Scheduler owns execution ordering.
    Private state: _level_queue, _running_futures, _node_worker_map.
    No access to dispatcher, state_store, retry_handler, or lease_manager state.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 23
    """

    def __init__(self) -> None:
        self._level_queue: List[List[Any]] = []
        self._running_futures: Dict[str, Future] = {}
        self._node_worker_map: Dict[str, str] = {}

    def schedule(
        self,
        dag: Any,
        session_id: Optional[str] = None,
        strategy: str = "balanced",
    ) -> List[List[Any]]:
        """Partition DAG nodes into execution levels.

        LAW 23: Only the scheduler may partition nodes.
        Returns levels of parallel-executable nodes.

        Args:
            dag: DependencyGraph to schedule.
            session_id: Optional session identifier.
            strategy: Scheduling strategy (balanced, cost_aware).

        Returns:
            List of levels, each level is a list of executable nodes.

        Raises:
            SchedulingError: If DAG contains cycles or invalid dependencies.
        """
        try:
            from core.models.dag import DependencyGraph
        except ImportError:
            # Fallback for testing without full DAG model
            if hasattr(dag, "topological_sort"):
                levels = dag.topological_sort(strategy=strategy)
            else:
                levels = self._simple_schedule(dag)
            self._level_queue = list(levels)
            logger.debug(
                "Scheduled %d levels (session=%s strategy=%s)",
                len(levels), session_id, strategy,
            )
            return self._level_queue

        if not isinstance(dag, DependencyGraph):
            levels = self._simple_schedule(dag)
            self._level_queue = list(levels)
            return self._level_queue

        levels = dag.topological_sort(strategy=strategy)
        self._level_queue = list(levels)
        logger.debug(
            "Scheduled %d levels from DependencyGraph (session=%s)",
            len(levels), session_id,
        )
        return self._level_queue

    def run_with_timeout(
        self,
        node: Any,
        runner: Callable[..., Any],
        timeout: float = 30.0,
    ) -> Any:
        """Execute a single node with timeout enforcement.

        Args:
            node: The node to execute.
            runner: Callable that executes the node's tool.
            timeout: Maximum wall-clock seconds.

        Returns:
            Node execution result.

        Raises:
            TimeoutError: If execution exceeds timeout.
        """
        node_id = str(getattr(node, "node_id", id(node)))
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runner, node)
            self._running_futures[node_id] = future
            try:
                result = future.result(timeout=timeout)
                return result
            except FutureTimeoutError:
                future.cancel()
                raise TimeoutError(
                    f"Node {node_id} exceeded timeout {timeout}s"
                )
            finally:
                self._running_futures.pop(node_id, None)

    def collect_futures(
        self,
        futures: Dict[Any, Any],
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Collect and process completed futures from a level.

        Args:
            futures: Dict mapping Future → Node.
            session_id: Optional session identifier.

        Returns:
            List of results in completion order.

        Raises:
            CollectError: If future collection encounters unhandled errors.
        """
        results: List[Dict[str, Any]] = []
        for future, node in futures.items():
            node_id = str(getattr(node, "node_id", id(node)))
            try:
                result = future.result(timeout=0.1)
                results.append({
                    "node_id": node_id,
                    "status": "completed",
                    "result": result,
                })
            except Exception as e:
                logger.warning("Collect failed for node %s: %s", node_id, e)
                raise CollectError(f"Failed to collect node {node_id}: {e}") from e
        return results

    @staticmethod
    def _simple_schedule(dag: Any) -> List[List[Any]]:
        """Simple topology sort for non-DependencyGraph inputs."""
        if hasattr(dag, "nodes"):
            nodes = list(dag.nodes)
        elif isinstance(dag, (list, tuple)):
            nodes = list(dag)
        else:
            nodes = [dag]
        return [nodes]
