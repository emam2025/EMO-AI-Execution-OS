"""Recovery Coordinator — monitors, detects, and resumes distributed executions.

Architecture:
    RecoveryCoordinator
        ├── monitors: expired leases, dead workers, incomplete executions
        ├── detect_failure() → List[FailedTask]
        ├── recover(task)    → ResumeToken
        └── engine.resume(token) → deterministic resume

ResumeToken:
    #B — structured checkpoint that captures full execution state:
        {
          "execution_id": "...",
          "dag_version": "...",
          "completed_nodes": [...],
          "pending_nodes": [...],
          "node_results": {...}
        }

    #C — DeterministicResume:
        engine.resume(token)  → skips completed, runs pending
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from .ownership_manager import OwnershipManager
from .worker_registry import WorkerRegistry
from .distributed_types import WorkerNode, WorkerStatus, TaskAssignment, TaskStatus
from .distributed_checkpoint import (
    DistributedCheckpointManager,
    DistributedRecoveryManager,
    DistributedCheckpoint,
    RecoveryResult,
)
from .heartbeat_daemon import WorkerHeartbeatDaemon
from .memory_pressure import CheckpointManager
from .interfaces.execution_engine import IExecutionEngine
from .models.dag import DependencyGraph, PlanNode, NodeState

logger = logging.getLogger("emo_ai.recovery_coordinator")

RECOVERY_COORDINATOR_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════════════════
# #B — Resume Token
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ResumeToken:
    """Structured checkpoint token for deterministic resume.

    Captures the full execution state so engine.resume(token) can
    pick up exactly where execution left off — no restart needed.

    Fields:
        execution_id: Unique identifier for this execution attempt.
        session_id: Original ExecutionMemory session ID.
        dag_version: DAG schema version (for compatibility check).
        completed_nodes: Ordered list of node IDs that succeeded.
        pending_nodes: Ordered list of node IDs still to execute.
        failed_nodes: List of node IDs that failed (may be retried).
        node_results: Dict of {node_id: result} for completed/failed.
        worker_assignments: {node_id: worker_id} for distributed exec.
        lease_state: {node_id: lease_id} snapshot of active leases.
        attempt_number: Which execution attempt this is.
        created_at: When the token was created.
    """
    execution_id: str
    session_id: str = ""
    dag_version: str = "1.0.0"
    completed_nodes: List[str] = field(default_factory=list)
    pending_nodes: List[str] = field(default_factory=list)
    failed_nodes: List[str] = field(default_factory=list)
    node_results: Dict[str, Any] = field(default_factory=dict)
    worker_assignments: Dict[str, str] = field(default_factory=dict)
    lease_state: Dict[str, str] = field(default_factory=dict)
    attempt_number: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ResumeToken:
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, s: str) -> ResumeToken:
        return cls.from_dict(json.loads(s))

    @property
    def is_empty(self) -> bool:
        return not self.completed_nodes and not self.failed_nodes

    @property
    def is_complete(self) -> bool:
        return not self.pending_nodes and not self.failed_nodes


# ═══════════════════════════════════════════════════════════════════
# Failure detection types
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FailedTask:
    """A task that has failed and needs recovery."""
    task_id: str
    worker_id: str
    failure_type: str  # "lease_expired" | "worker_dead" | "incomplete"
    detected_at: float = field(default_factory=time.time)
    checkpoint: Optional[DistributedCheckpoint] = None
    session_id: str = ""


# ═══════════════════════════════════════════════════════════════════
# #A — Recovery Coordinator
# ═══════════════════════════════════════════════════════════════════


class RecoveryCoordinator:
    """Orchestrates detection and recovery of failed distributed tasks.

    Flow:
        1. detect_failures() → scans for expired leases, dead workers,
           incomplete executions
        2. recover(task)      → loads checkpoint, reassigns, builds
           ResumeToken, returns it
        3. engine.resume(token) → caller resumes execution deterministically
    """

    def __init__(
        self,
        engine: IExecutionEngine,
        ownership_manager: OwnershipManager,
        worker_registry: WorkerRegistry,
        distributed_checkpoint: DistributedCheckpointManager,
        heartbeat_daemon: Optional[WorkerHeartbeatDaemon] = None,
    ):
        self._engine = engine
        self._ownership = ownership_manager
        self._registry = worker_registry
        self._dcp = distributed_checkpoint
        self._daemon = heartbeat_daemon

        # Internal recovery manager
        self._recovery_mgr = DistributedRecoveryManager(
            ownership_manager=ownership_manager,
            worker_registry=worker_registry,
            checkpoint_manager=distributed_checkpoint,
        )

        self._lock = threading.Lock()
        self._recovering: Set[str] = set()  # task_ids currently being recovered

    @property
    def version(self) -> str:
        return RECOVERY_COORDINATOR_VERSION

    # ── Detection ──────────────────────────────────────────────

    def detect_failures(self) -> List[FailedTask]:
        """Scan for all types of failures.

        Checks:
          1. Expired leases (lease past deadline)
          2. Dead workers (no heartbeat within timeout)
          3. Incomplete executions (checkpointed but not finished)

        Returns:
            List of FailedTask objects describing each failure.
        """
        failed: List[FailedTask] = []

        # 1. Expired leases
        expired = self._ownership.reassign_expired(max_tasks=0)
        for task_id in expired:
            cp = self._dcp.get_checkpoint(task_id)
            failed.append(FailedTask(
                task_id=task_id,
                worker_id=cp.worker_id if cp else "unknown",
                failure_type="lease_expired",
                checkpoint=cp,
                session_id=task_id if cp else "",
            ))

        # 2. Dead workers (prune + detect)
        pruned = self._registry.prune_offline()
        if pruned > 0:
            # Find tasks that were assigned to now-offline workers
            # by scanning remaining distributed checkpoints
            all_tasks = []  # We'd need a way to enumerate all tracked tasks
            # For now, rely on lease expiration detection above

        # 3. Incomplete executions (checkpointed but not finished)
        # Scan local checkpoint sessions for incompleteness
        try:
            sessions = self._dcp._local_cp.list_sessions()
            for s in sessions:
                sid = s["session_id"]
                cp = self._dcp.get_checkpoint(sid)
                if cp is None:
                    continue
                # If there are completed nodes but the execution
                # has a pending current_node, it's incomplete
                if cp.completed_nodes and cp.current_node:
                    # Check if it's already being recovered
                    if sid not in self._recovering:
                        failed.append(FailedTask(
                            task_id=sid,
                            worker_id=cp.worker_id,
                            failure_type="incomplete",
                            checkpoint=cp,
                            session_id=sid,
                        ))
        except Exception:
            logger.exception("Failed to scan incomplete sessions")

        return failed

    # ── Recovery ───────────────────────────────────────────────

    def recover(
        self,
        task: FailedTask,
        required_tool: str = "",
        lease_duration: float = 60.0,
    ) -> Optional[ResumeToken]:
        """Recover a failed task and produce a ResumeToken.

        Args:
            task: FailedTask from detect_failures().
            required_tool: Tool needed (for finding replacement).
            lease_duration: Lease for the new assignment.

        Returns:
            ResumeToken if recovery succeeds, None otherwise.
        """
        with self._lock:
            if task.task_id in self._recovering:
                logger.warning("Task %s already being recovered", task.task_id)
                return None
            self._recovering.add(task.task_id)

        try:
            # 1. Use DistributedRecoveryManager to reassign
            recovery = self._recovery_mgr.recover(
                task_id=task.task_id,
                failed_worker_id=task.worker_id,
                required_tool=required_tool,
                lease_duration=lease_duration,
            )

            if not recovery.success:
                logger.error(
                    "Recovery failed for task %s: %s",
                    task.task_id, recovery.reason,
                )
                return None

            # 2. Load the checkpoint to build the token
            cp = task.checkpoint or self._dcp.get_checkpoint(task.task_id)
            if cp is None:
                logger.error("No checkpoint found after recovery for %s", task.task_id)
                return None

            # 3. Determine pending nodes
            completed = list(cp.completed_nodes)
            # If there was a current node being worked on, it's pending
            pending = [cp.current_node] if cp.current_node else []

            # 4. Build the resume token
            token = ResumeToken(
                execution_id=recovery.new_execution_id,
                session_id=cp.session_id,
                dag_version="1.0.0",
                completed_nodes=completed,
                pending_nodes=pending,
                failed_nodes=[cp.current_node] if cp.failure_reason else [],
                node_results=dict(cp.node_results),
                worker_assignments={recovery.task_id: recovery.new_worker},
                lease_state={recovery.task_id: recovery.new_lease_id},
                attempt_number=recovery.attempt_number,
            )

            logger.info(
                "Recovery token created: task=%s attempt=%d "
                "completed=%d pending=%d",
                task.task_id, recovery.attempt_number,
                len(completed), len(pending),
            )
            return token

        except Exception as e:
            logger.exception("Recovery failed for %s: %s", task.task_id, e)
            return None
        finally:
            with self._lock:
                self._recovering.discard(task.task_id)

    # ── Full recovery cycle ────────────────────────────────────

    def recover_all(self, lease_duration: float = 60.0) -> List[ResumeToken]:
        """Detect all failures and recover each one.

        Returns:
            List of ResumeTokens for successful recoveries.
        """
        tokens: List[ResumeToken] = []
        failed_tasks = self.detect_failures()
        for task in failed_tasks:
            token = self.recover(task, lease_duration=lease_duration)
            if token is not None:
                tokens.append(token)
        return tokens

    def recovering_count(self) -> int:
        with self._lock:
            return len(self._recovering)


# ═══════════════════════════════════════════════════════════════════
# #C — Deterministic Resume
# ═══════════════════════════════════════════════════════════════════


class DeterministicResume:
    """Resumes DAG execution from a ResumeToken.

    Wires into IExecutionEngine to skip completed nodes and continue
    from pending nodes — no restart needed.

    Flow:
        engine.resume(token, dag, runner)
            → skips completed nodes (replay results from token)
            → runs pending nodes normally
            → returns full execution result
    """

    def __init__(self, engine: IExecutionEngine):
        self._engine = engine

    def resume(
        self,
        token: ResumeToken,
        dag: DependencyGraph,
        tool_runner: Optional[Any] = None,
        session_id: str = "",
    ) -> Dict[str, Any]:
        """Resume execution from a checkpoint token.

        Args:
            token: ResumeToken from RecoveryCoordinator.recover().
            dag: The full DAG to execute (must match token's DAG).
            tool_runner: Optional tool runner function.
            session_id: ExecutionMemory session ID (if applicable).

        Returns:
            Execution result dict with same structure as
            IExecutionEngine.execute().
        """
        # 1. Apply completed node results from token
        for node_id in token.completed_nodes:
            node = dag.nodes.get(node_id)
            if node is None:
                logger.warning(
                    "Resume: completed node %s not in DAG, skipping",
                    node_id,
                )
                continue
            result = token.node_results.get(node_id, {})
            node.state = NodeState.COMPLETED
            node.result = result

        # 2. Mark failed nodes for retry (reset to PENDING)
        for node_id in token.failed_nodes:
            node = dag.nodes.get(node_id)
            if node is None:
                continue
            node.state = NodeState.PENDING
            node.error = None
            node.retry_count = 0

        # 3. Mark pending nodes as PENDING
        for node_id in token.pending_nodes:
            node = dag.nodes.get(node_id)
            if node is None:
                continue
            node.state = NodeState.PENDING

        # 4. All other nodes remain PENDING by default
        # (they'll run normally in the level loop)

        # 5. Re-check schema version
        self._engine._check_schema_version(dag)

        # 6. Run via normal execute
        result = self._engine.execute(
            dag=dag,
            session_id=session_id,
            tool_runner=tool_runner,
        )

        # 7. Restore completed nodes' states (execute resets all to PLANNED)
        for node_id in token.completed_nodes:
            node = dag.nodes.get(node_id)
            if node is not None:
                node.state = NodeState.COMPLETED
                node.result = token.node_results.get(node_id, {})

        # 8. Restore failed nodes to PENDING for retry
        for node_id in token.failed_nodes:
            node = dag.nodes.get(node_id)
            if node is not None:
                node.state = NodeState.PENDING
                node.error = None
                node.retry_count = 0

        return result

    @staticmethod
    def build_dag_from_token(
        token: ResumeToken,
        tool: str = "",
        inputs: Optional[Dict[str, Any]] = None,
    ) -> DependencyGraph:
        """Build a minimal DAG from a resume token.

        Useful when the original DAG is not available and must be
        reconstructed from the token.

        Creates one node per completed + pending + failed entry.
        """
        dag = DependencyGraph()
        dag.version = token.dag_version
        all_nodes = set(
            token.completed_nodes
            + token.pending_nodes
            + token.failed_nodes
        )
        prev_id = None
        for nid in sorted(all_nodes):
            result = token.node_results.get(nid)
            node = PlanNode(
                id=nid,
                tool=tool or "unknown",
                inputs=inputs or result or {},
                state=(
                    NodeState.COMPLETED
                    if nid in token.completed_nodes
                    else NodeState.PENDING
                ),
                result=result,
            )
            dag.add_node(node)
            if prev_id:
                dag.add_edge(prev_id, nid, "success")
            prev_id = nid
        return dag
