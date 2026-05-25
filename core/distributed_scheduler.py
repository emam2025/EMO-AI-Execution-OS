"""Distributed Scheduler — load-aware task → worker assignment.

Architecture:
    ExecutionEngine._execute_node
        ↓
    DistributedScheduler.schedule(tasks, registry)
        ↓
    List[TaskAssignment]  +  List[unassigned_tasks]
        ↓
    Engine dispatches to remote workers or falls back to local

Strategy:
    - Least-loaded first (minimize queue depth)
    - Tool-aware (only workers that support the tool)
    - Tag-aware (optional affinity)
    - Capacity-respecting
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set
from uuid import uuid4

from .distributed_types import (
    TaskAssignment, TaskStatus, WorkerNode,
)
from .models.dag import PlanNode
from .worker_registry import WorkerRegistry

logger = logging.getLogger("emo_ai.distributed_scheduler")

SCHEDULER_VERSION = "1.0.0"


class DistributedScheduler:
    """Assigns DAG nodes to distributed workers.

    Thread-safe when paired with a thread-safe WorkerRegistry.
    The scheduler itself is stateless — all state lives in the registry.
    """

    def __init__(
        self,
        registry: WorkerRegistry,
        tag_affinity: Optional[Dict[str, str]] = None,
    ):
        self._registry = registry
        self._tag_affinity = tag_affinity or {}

    @property
    def version(self) -> str:
        return SCHEDULER_VERSION

    def schedule(
        self,
        nodes: List[PlanNode],
    ) -> tuple[List[TaskAssignment], List[PlanNode]]:
        """Assign nodes to workers.

        Args:
            nodes: DAG nodes ready for execution (same topological level).

        Returns:
            (assignments, unassigned):
                assignments: List[TaskAssignment] — tasks sent to workers.
                unassigned: List[PlanNode] — nodes that could not be
                            assigned and should run locally.
        """
        if not nodes:
            return [], []

        assignments: List[TaskAssignment] = []
        unassigned: List[PlanNode] = []

        # Group nodes by tool for efficient worker lookup
        by_tool: Dict[str, List[PlanNode]] = {}
        for node in nodes:
            by_tool.setdefault(node.tool, []).append(node)

        for tool, tool_nodes in by_tool.items():
            remaining = list(tool_nodes)

            # Phase 1: assign to available (IDLE + capacity) workers
            while remaining:
                worker = self._registry.any_worker_for(tool)
                if worker is None:
                    break  # no more candidates
                node = remaining.pop(0)
                assignment = self._assign(node, worker)
                assignments.append(assignment)
                self._registry.increment_load(worker.id)

            # Phase 2: also consider BUSY workers that still have capacity
            if remaining:
                all_workers = self._registry.list_workers()
                candidates = [
                    w for w in all_workers
                    if w.supports_tool(tool) and w.available_capacity > 0
                ]
                # Sort by available capacity descending (most free first)
                candidates.sort(
                    key=lambda w: w.available_capacity, reverse=True,
                )
                for worker in candidates:
                    if not remaining:
                        break
                    node = remaining.pop(0)
                    assignment = self._assign(node, worker)
                    assignments.append(assignment)
                    self._registry.increment_load(worker.id)

            # Phase 3: tag-affinity scheduling for unassigned
            if remaining and self._tag_affinity:
                tagged = self._registry.workers_by_tag(
                    *next(iter(self._tag_affinity.items()))
                )
                for worker in tagged:
                    if not remaining:
                        break
                    if not worker.supports_tool(tool):
                        continue
                    if worker.available_capacity <= 0:
                        continue
                    node = remaining.pop(0)
                    assignment = self._assign(node, worker)
                    assignments.append(assignment)
                    self._registry.increment_load(worker.id)

            # Whatever is left → local execution
            unassigned.extend(remaining)

        return assignments, unassigned

    def release(self, assignment: TaskAssignment) -> None:
        """Release a worker's capacity after a task completes.

        Should be called by the engine when a remote task finishes
        (success or failure).
        """
        if assignment.worker_id:
            self._registry.decrement_load(assignment.worker_id)

    @staticmethod
    def _assign(node: PlanNode, worker: WorkerNode) -> TaskAssignment:
        return TaskAssignment(
            task_id=str(uuid4()),
            tool=node.tool,
            inputs=dict(node.inputs),
            worker_id=worker.id,
            status=TaskStatus.PENDING,
        )
