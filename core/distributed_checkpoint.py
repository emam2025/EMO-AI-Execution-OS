"""Distributed Checkpoint Recovery — resume execution from last checkpoint on worker failure.

Architecture:
    ExecutionEngine
        ├── CheckpointManager            (local per-node checkpoint)
        ├── DistributedCheckpointManager ← YOU ARE HERE
        │       (adds lease/ownership/worker context to checkpoints)
        └── DistributedRecoveryManager   ← AND HERE
                (detects worker death, reassigns, resumes from checkpoint)

Flow:
    Normal execution:
        For each node → save checkpoint with ownership context
        If node completed → checkpoint with result + lease release

    Worker failure (detected by HeartbeatDaemon):
        1. DistributedRecoveryManager.recover(task_id, failed_worker)
        2. Load last checkpoint for task
        3. Reassign to available worker
        4. New worker resumes: skip completed nodes, retry failed node
        5. Increment attempt_number, new execution_id
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from .memory_pressure import CheckpointManager
from .ownership_manager import OwnershipManager
from .worker_registry import WorkerRegistry
from .distributed_types import WorkerNode, WorkerStatus, TaskAssignment

logger = logging.getLogger("emo_ai.distributed_checkpoint")

DISTRIBUTED_CHECKPOINT_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DistributedCheckpoint:
    """Checkpoint snapshot for a single task in a distributed execution.

    Adds ownership and execution context to the basic result checkpoint.
    """
    task_id: str
    session_id: str
    worker_id: str
    lease_id: str
    execution_id: str
    attempt_number: int

    # What was completed before this checkpoint
    completed_nodes: Set[str] = field(default_factory=set)
    node_results: Dict[str, Any] = field(default_factory=dict)

    # What was in progress when checkpoint was taken
    current_node: str = ""
    current_node_inputs: Dict[str, Any] = field(default_factory=dict)

    # Failure info (set on recovery path)
    failed_at: Optional[float] = None
    failure_reason: str = ""

    created_at: float = field(default_factory=time.time)


@dataclass
class RecoveryResult:
    """Result of a distributed recovery operation."""
    success: bool
    task_id: str
    original_worker: str
    new_worker: str = ""
    new_lease_id: str = ""
    new_execution_id: str = ""
    attempt_number: int = 0
    completed_nodes: Set[str] = field(default_factory=set)
    current_node: str = ""
    reason: str = ""


# ═══════════════════════════════════════════════════════════════════
# Distributed Checkpoint Manager
# ═══════════════════════════════════════════════════════════════════


class DistributedCheckpointManager:
    """Extends CheckpointManager with distributed execution context.

    Stores per-task checkpoints that include:
      - Which worker owned the lease
      - Which nodes were completed
      - Which node was in progress
      - Execution ID and attempt number

    Thread-safe. Uses local CheckpointManager for result persistence
    and an in-memory index for distributed context.
    """

    def __init__(
        self,
        checkpoint_manager: Optional[CheckpointManager] = None,
    ):
        self._local_cp = checkpoint_manager or CheckpointManager()
        self._lock = threading.Lock()
        # In-memory accumulators: session_id -> {node_id: result}
        self._results: Dict[str, Dict[str, Any]] = {}
        self._dcp: Dict[str, DistributedCheckpoint] = {}

    @property
    def version(self) -> str:
        return DISTRIBUTED_CHECKPOINT_VERSION

    # ── Save ───────────────────────────────────────────────────

    def save_node(
        self,
        session_id: str,
        node_id: str,
        result: Dict[str, Any],
        *,
        dag=None,
        worker_id: str = "",
        lease_id: str = "",
        execution_id: str = "",
        attempt_number: int = 0,
        completed_nodes: Optional[Set[str]] = None,
        current_node: str = "",
        current_node_inputs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Save a per-node checkpoint with distributed context.

        Args:
            session_id: Execution session ID.
            node_id: The node that just completed.
            result: Node execution result.
            dag: Optional DependencyGraph snapshot (stored once).
            worker_id: Worker that executed the node.
            lease_id: Lease for this task.
            execution_id: Unique execution attempt ID.
            attempt_number: Which attempt (0 = first).
            completed_nodes: Set of all completed node IDs.
            current_node: Node currently in progress (if any).
            current_node_inputs: Inputs for the current node.
        """
        # Save result to local checkpoint store
        if dag is not None:
            self._local_cp.save(session_id, dag, node_id, result)

        # Track results in memory
        with self._lock:
            if session_id not in self._results:
                self._results[session_id] = {}
            self._results[session_id][node_id] = result

            all_results = dict(self._results[session_id])

            # Track distributed context in memory
            dcp = DistributedCheckpoint(
                task_id=session_id,
                session_id=session_id,
                worker_id=worker_id,
                lease_id=lease_id,
                execution_id=execution_id,
                attempt_number=attempt_number,
                completed_nodes=set(completed_nodes or set()) | {node_id},
                node_results=all_results,
                current_node=current_node,
                current_node_inputs=dict(current_node_inputs or {}),
            )
            self._dcp[session_id] = dcp

        logger.debug(
            "Distributed checkpoint: task=%s node=%s worker=%s "
            "(completed=%d)",
            session_id, node_id, worker_id, len(dcp.completed_nodes),
        )

    def save_failure(
        self,
        session_id: str,
        node_id: str,
        error: str,
        *,
        dag=None,
        worker_id: str = "",
        lease_id: str = "",
        execution_id: str = "",
        attempt_number: int = 0,
        completed_nodes: Optional[Set[str]] = None,
    ) -> None:
        """Save a failure checkpoint.

        Records which node failed and why, so recovery can resume
        from the last good state.
        """
        result = {"status": "failed", "error": error, "node_id": node_id}
        if dag is not None:
            self._local_cp.save(session_id, dag, node_id, result)

        with self._lock:
            if session_id not in self._results:
                self._results[session_id] = {}
            self._results[session_id][node_id] = result

            dcp = DistributedCheckpoint(
                task_id=session_id,
                session_id=session_id,
                worker_id=worker_id,
                lease_id=lease_id,
                execution_id=execution_id,
                attempt_number=attempt_number,
                completed_nodes=set(completed_nodes or set()),
                node_results=dict(self._results.get(session_id, {})),
                current_node=node_id,
                failure_reason=error,
            )
            self._dcp[session_id] = dcp

    # ── Load ───────────────────────────────────────────────────

    def get_checkpoint(self, task_id: str) -> Optional[DistributedCheckpoint]:
        """Get the latest distributed checkpoint for a task."""
        with self._lock:
            return self._dcp.get(task_id)

    def get_completed(self, session_id: str) -> Set[str]:
        """Get completed node IDs from local store."""
        return self._local_cp.completed_nodes(session_id)

    def clear(self) -> None:
        """Clear all distributed checkpoints (for testing)."""
        with self._lock:
            self._dcp.clear()


# ═══════════════════════════════════════════════════════════════════
# Distributed Recovery Manager
# ═══════════════════════════════════════════════════════════════════


class DistributedRecoveryManager:
    """Handles recovery when a worker fails during distributed execution.

    Flow:
        1. HeartbeatDaemon detects worker failure and calls recover()
        2. RecoveryManager loads the last checkpoint for the task
        3. Assigns the task to a new available worker
        4. New worker claims the lease (with incremented attempt)
        5. Returns RecoveryResult describing the recovery plan
    """

    def __init__(
        self,
        ownership_manager: OwnershipManager,
        worker_registry: WorkerRegistry,
        checkpoint_manager: DistributedCheckpointManager,
    ):
        self._ownership = ownership_manager
        self._registry = worker_registry
        self._dcp = checkpoint_manager

    @property
    def version(self) -> str:
        return DISTRIBUTED_CHECKPOINT_VERSION

    def recover(
        self,
        task_id: str,
        failed_worker_id: str,
        required_tool: str = "",
        lease_duration: float = 60.0,
    ) -> RecoveryResult:
        """Recover a task from a failed worker.

        Args:
            task_id: The task that was being executed on the failed worker.
            failed_worker_id: The worker that died.
            required_tool: Tool required (for finding a replacement).
            lease_duration: Lease duration for the new assignment.

        Returns:
            RecoveryResult: success status and recovery plan.
        """
        # 1. Load checkpoint
        cp = self._dcp.get_checkpoint(task_id)
        if cp is None:
            return RecoveryResult(
                success=False,
                task_id=task_id,
                original_worker=failed_worker_id,
                reason=f"No checkpoint found for task {task_id}",
            )

        # 2. Verify ownership
        owner = self._ownership.owner_of(task_id)
        if owner is not None and owner != failed_worker_id:
            return RecoveryResult(
                success=False,
                task_id=task_id,
                original_worker=failed_worker_id,
                reason=(
                    f"Task {task_id} now owned by {owner}, "
                    f"not failed worker {failed_worker_id}"
                ),
            )

        # 3. Release the old lease
        if cp.lease_id:
            self._ownership.release(task_id, cp.lease_id)

        # 4. Find a replacement worker
        tool = required_tool or (
            cp.current_node
            # Try to infer tool from current node — caller should provide
        )

        replacement: Optional[WorkerNode] = None
        if tool:
            replacement = self._registry.any_worker_for(tool)
        if replacement is None:
            # Try any available worker
            for w in self._registry.list_workers():
                if w.status != WorkerStatus.OFFLINE and w.available_capacity > 0:
                    replacement = w
                    break

        if replacement is None:
            return RecoveryResult(
                success=False,
                task_id=task_id,
                original_worker=failed_worker_id,
                reason="No available worker for recovery",
            )

        # 5. Claim the task on the new worker
        new_attempt = cp.attempt_number + 1
        new_execution_id = str(uuid4())
        new_lease = self._ownership.claim(
            task_id=task_id,
            worker_id=replacement.id,
            lease_duration=lease_duration,
            execution_id=new_execution_id,
            attempt_number=new_attempt,
        )
        if new_lease is None:
            return RecoveryResult(
                success=False,
                task_id=task_id,
                original_worker=failed_worker_id,
                reason="Failed to claim lease on replacement worker",
            )

        # 6. Update worker load
        self._registry.increment_load(replacement.id)

        # 7. Return recovery plan
        result = RecoveryResult(
            success=True,
            task_id=task_id,
            original_worker=failed_worker_id,
            new_worker=replacement.id,
            new_lease_id=new_lease,
            new_execution_id=new_execution_id,
            attempt_number=new_attempt,
            completed_nodes=cp.completed_nodes,
            current_node=cp.current_node,
            reason=(
                f"Recovered from worker {failed_worker_id} → "
                f"{replacement.id} (attempt {new_attempt})"
            ),
        )

        logger.info(
            "Recovery: task %s from worker %s → %s "
            "(attempt %d, %d nodes completed)",
            task_id, failed_worker_id, replacement.id,
            new_attempt, len(cp.completed_nodes),
        )
        return result

    def can_recover(self, task_id: str, worker_id: str) -> bool:
        """Quick check if a task can be recovered."""
        cp = self._dcp.get_checkpoint(task_id)
        if cp is None:
            return False
        # Task must have been assigned to this worker
        if cp.worker_id != worker_id:
            return False
        # There must be some progress or a failure
        return bool(cp.completed_nodes) or bool(cp.failure_reason)

    def count_pending(self) -> int:
        """Count tasks with checkpoints that have NOT been recovered."""
        # This is used by engine to know if there are pending recoveries
        return 0  # Placeholder — will be extended with a pending queue
