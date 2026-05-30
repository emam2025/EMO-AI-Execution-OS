"""Deterministic Distributed Replay — full execution reproduction.

Extends the existing DAGReplayEngine with distributed execution context:
  - Ownership transitions (lease claims, renewals, releases)
  - Worker assignments per node
  - Retry attempts with timing
  - Timing classes (fast/medium/slow path)

Architecture:
    ExecutionEngine
        └── store_distributed_trace() → ExecutionMemory
                └── DistributedReplayEngine.rebuild()
                        └── DistributedReplaySession
                                ├── steps() — full step-by-step replay
                                ├── ownership_timeline() — lease events
                                ├── timing_report() — timing classification
                                └── compare() — deterministic diff
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .execution_memory import ExecutionMemory
from .models.dag import (
    DependencyGraph, PlanNode, PlanEdge, NodeState,
)

logger = logging.getLogger("emo_ai.distributed_replay")

DISTRIBUTED_REPLAY_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════


class TimingClass(str, Enum):
    """Execution timing classification for replay.

    Enables deterministic timing reproduction:
      - FAST:     < 100ms  (instant replay)
      - MEDIUM:   < 1s     (normal replay with pacing)
      - SLOW:     >= 1s    (paced replay with wait)
      - TIMEOUT:  exceeded deadline
    """
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    TIMEOUT = "timeout"


class LeaseEventType(str, Enum):
    CLAIM = "claim"
    RENEW = "renew"
    RELEASE = "release"
    EXPIRE = "expire"
    RECOVER = "recover"


# ═══════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════


@dataclass
class LeaseEvent:
    """A single ownership transition event."""
    event_type: LeaseEventType
    task_id: str
    worker_id: str
    lease_id: str
    execution_id: str = ""
    attempt_number: int = 0
    timestamp: float = 0.0
    duration_ms: float = 0.0


@dataclass
class DistributedReplayStep:
    """A single node execution step in distributed replay.

    Extends the basic ReplayStep with distributed context.
    """
    node_id: str
    tool: str
    inputs: Dict[str, Any]
    state: str
    duration_ms: float
    retry_count: int
    attempt_number: int
    error: Optional[str]
    output_summary: str
    worker_id: str = ""
    timing_class: str = "unknown"
    lease_events: List[LeaseEvent] = field(default_factory=list)
    execution_id: str = ""


@dataclass
class DistributedReplaySession:
    """A fully reconstructed distributed execution session."""
    session_id: str
    query: str
    strategy: str
    status: str
    started_at: float
    completed_at: Optional[float]
    total_duration_ms: float
    node_count: int
    edge_count: int
    steps: List[DistributedReplayStep]
    graph: DependencyGraph
    raw_trace: Dict[str, Any]
    ownership_timeline: List[LeaseEvent] = field(default_factory=list)
    worker_count: int = 0
    unique_workers: Set[str] = field(default_factory=set)
    total_retries: int = 0
    timing_distribution: Dict[str, int] = field(default_factory=dict)


@dataclass
class DistributedRunComparison:
    """Deterministic comparison of two distributed executions."""
    session_a: str
    session_b: str
    query_a: str
    query_b: str
    total_duration_delta_ms: float
    node_count_delta: int
    status_match: bool
    tool_diff: List[str]
    ownership_match: bool = True
    retry_count_delta: int = 0
    worker_diff: List[str] = field(default_factory=list)
    timing_diff: List[str] = field(default_factory=list)
    node_comparisons: List[Dict[str, Any]] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# Timing classifier
# ═══════════════════════════════════════════════════════════════════


def classify_timing(duration_ms: float) -> TimingClass:
    """Classify a node execution duration into a timing class."""
    if duration_ms < 100:
        return TimingClass.FAST
    if duration_ms < 1000:
        return TimingClass.MEDIUM
    if duration_ms < 30000:
        return TimingClass.SLOW
    return TimingClass.TIMEOUT


# ═══════════════════════════════════════════════════════════════════
# Distributed Replay Engine
# ═══════════════════════════════════════════════════════════════════


class DistributedReplayEngine:
    """Replay distributed DAG executions with full distributed context.

    Reads distributed execution traces from ExecutionMemory and
    reconstructs a DeterministicReplaySession that includes:
      - Per-node worker assignments
      - Ownership transition timeline
      - Retry attempts with timing
      - Timing class distribution
    """

    def __init__(self, memory: ExecutionMemory):
        self.memory = memory

    @property
    def version(self) -> str:
        return DISTRIBUTED_REPLAY_VERSION

    # ── Session listing ─────────────────────────────────────────

    def available_sessions(
        self, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List sessions with distributed traces available."""
        sessions = self.memory.recent_sessions(limit=limit)
        result = []
        for s in sessions:
            trace = self.memory.get_dag_trace(s.session_id)
            if trace is None:
                continue
            distributed = trace.get("distributed", {})
            entry = {
                "session_id": s.session_id,
                "query": s.query,
                "strategy": s.strategy,
                "status": s.status,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
                "node_count": len(trace.get("nodes", {})),
                "worker_count": len(distributed.get("workers", {})),
                "total_retries": distributed.get("total_retries", 0),
                "timing_classes": distributed.get("timing_classes", {}),
            }
            result.append(entry)
        return result

    # ── Rebuild ─────────────────────────────────────────────────

    def rebuild(self, session_id: str) -> Optional[DistributedReplaySession]:
        """Rebuild a full DistributedReplaySession from stored trace.

        The trace must contain a 'distributed' key with:
            workers: {worker_id: url, ...}
            leases: [LeaseEvent, ...]
            total_retries: int
            timing_classes: {class: count, ...}
        """
        trace = self.memory.get_dag_trace(session_id)
        if trace is None:
            return None

        sess = self.memory.get_session(session_id)
        if sess is None:
            return None

        # Reconstruct graph
        dag = DependencyGraph()
        raw_nodes = trace.get("nodes", {})
        raw_edges = trace.get("edges", [])

        for nid, ndata in raw_nodes.items():
            dag.add_node(PlanNode(
                id=nid,
                tool=ndata.get("tool", "?"),
                inputs=ndata.get("inputs", {}),
                state=NodeState(ndata.get("state", "pending")),
                started_at=ndata.get("started_at"),
                completed_at=ndata.get("completed_at"),
                retry_count=ndata.get("retry_count", 0),
                error=ndata.get("error"),
                result=ndata.get("result"),
            ))

        for edata in raw_edges:
            dag.add_edge(
                edata.get("source_id") or edata.get("source", ""),
                edata.get("target_id") or edata.get("target", ""),
                edata.get("condition", "success"),
            )

        # Parse distributed metadata
        distributed = trace.get("distributed", {})
        raw_leases = distributed.get("leases", [])
        ownership_timeline = [
            LeaseEvent(
                event_type=LeaseEventType(le.get("event_type", "claim")),
                task_id=le.get("task_id", ""),
                worker_id=le.get("worker_id", ""),
                lease_id=le.get("lease_id", ""),
                execution_id=le.get("execution_id", ""),
                attempt_number=le.get("attempt_number", 0),
                timestamp=le.get("timestamp", 0.0),
                duration_ms=le.get("duration_ms", 0.0),
            )
            for le in raw_leases
        ]

        workers = distributed.get("workers", {})
        unique_workers = set(workers.keys())

        # Build steps with distributed context
        steps: List[DistributedReplayStep] = []
        topo_order = [n.id for n in dag.topo_sort()]
        for node_id in topo_order:
            ndata = raw_nodes.get(node_id, {})
            duration_ms = 0.0
            if ndata.get("started_at") and ndata.get("completed_at"):
                duration_ms = (ndata["completed_at"] - ndata["started_at"]) * 1000

            # Collect lease events for this node
            node_leases = [
                le for le in ownership_timeline
                if le.task_id == node_id
            ]

            attempt_number = ndata.get("attempt_number", 0)
            execution_id = ndata.get("execution_id", "")
            worker_id = ndata.get("worker_id", "")
            timing_class = classify_timing(duration_ms).value

            result = ndata.get("result")
            output_summary = json.dumps(result)[:120] if result else ""

            steps.append(DistributedReplayStep(
                node_id=node_id,
                tool=ndata.get("tool", "?"),
                inputs=ndata.get("inputs", {}),
                state=ndata.get("state", "pending"),
                duration_ms=duration_ms,
                retry_count=ndata.get("retry_count", 0),
                attempt_number=attempt_number,
                error=ndata.get("error"),
                output_summary=output_summary,
                worker_id=worker_id,
                timing_class=timing_class,
                lease_events=node_leases,
                execution_id=execution_id,
            ))

        # Compute session-level metrics
        total_duration_ms = 0.0
        if sess.started_at:
            end = sess.completed_at or time.time()
            total_duration_ms = (end - sess.started_at) * 1000

        total_retries = sum(s.retry_count for s in steps)
        timing_distribution = distributed.get("timing_classes", {})
        if not timing_distribution:
            tc: Dict[str, int] = {}
            for s in steps:
                tc[s.timing_class] = tc.get(s.timing_class, 0) + 1
            timing_distribution = tc

        return DistributedReplaySession(
            session_id=session_id,
            query=sess.query,
            strategy=sess.strategy,
            status=sess.status,
            started_at=sess.started_at,
            completed_at=sess.completed_at,
            total_duration_ms=total_duration_ms,
            node_count=len(dag.nodes),
            edge_count=len(dag.edges),
            steps=steps,
            graph=dag,
            raw_trace=trace,
            ownership_timeline=ownership_timeline,
            worker_count=len(unique_workers),
            unique_workers=unique_workers,
            total_retries=total_retries,
            timing_distribution=timing_distribution,
        )

    # ── Comparison ─────────────────────────────────────────────

    def compare(
        self,
        session_a: str,
        session_b: str,
    ) -> Optional[DistributedRunComparison]:
        """Deterministic diff of two distributed executions.

        Compares DAG structure, ownership transitions, retry counts,
        worker assignments, and timing distributions.
        """
        sa = self.rebuild(session_a)
        sb = self.rebuild(session_b)
        if sa is None or sb is None:
            return None

        # DAG structure diff
        tools_a = {s.tool for s in sa.steps}
        tools_b = {s.tool for s in sb.steps}
        tool_diff = sorted(
            [f"+{t}" for t in tools_b - tools_a]
            + [f"-{t}" for t in tools_a - tools_b]
        )

        # Ownership match
        lease_a = [(le.event_type, le.worker_id) for le in sa.ownership_timeline]
        lease_b = [(le.event_type, le.worker_id) for le in sb.ownership_timeline]
        ownership_match = lease_a == lease_b

        # Worker assignments
        workers_a = sa.unique_workers
        workers_b = sb.unique_workers
        worker_diff = sorted(
            [f"+{w}" for w in workers_b - workers_a]
            + [f"-{w}" for w in workers_a - workers_b]
        )

        # Timing diff
        timing_diff = []
        all_classes = set(sa.timing_distribution) | set(sb.timing_distribution)
        for tc in sorted(all_classes):
            ca = sa.timing_distribution.get(tc, 0)
            cb = sb.timing_distribution.get(tc, 0)
            if ca != cb:
                timing_diff.append(f"{tc}: {ca}→{cb}")

        # Per-node comparisons
        node_comparisons: List[Dict[str, Any]] = []
        steps_a = {s.node_id: s for s in sa.steps}
        steps_b = {s.node_id: s for s in sb.steps}
        all_nodes = set(steps_a) | set(steps_b)
        for nid in sorted(all_nodes):
            a = steps_a.get(nid)
            b = steps_b.get(nid)
            comp = {
                "node_id": nid,
                "tool_match": a.tool == b.tool if a and b else False,
                "state_match": a.state == b.state if a and b else False,
                "duration_delta_ms": (
                    (b.duration_ms - a.duration_ms)
                    if a and b else 0
                ),
                "retry_delta": (
                    b.retry_count - a.retry_count
                    if a and b else 0
                ),
                "errors_match": (
                    (a.error or "") == (b.error or "")
                    if a and b else False
                ),
                "worker_match": (
                    a.worker_id == b.worker_id
                    if a and b else False
                ),
                "timing_class_a": a.timing_class if a else "?",
                "timing_class_b": b.timing_class if b else "?",
            }
            node_comparisons.append(comp)

        return DistributedRunComparison(
            session_a=session_a,
            session_b=session_b,
            query_a=sa.query,
            query_b=sb.query,
            total_duration_delta_ms=sb.total_duration_ms - sa.total_duration_ms,
            node_count_delta=sb.node_count - sa.node_count,
            status_match=sa.status == sb.status,
            tool_diff=tool_diff,
            ownership_match=ownership_match,
            retry_count_delta=sb.total_retries - sa.total_retries,
            worker_diff=worker_diff,
            timing_diff=timing_diff,
            node_comparisons=node_comparisons,
        )

    # ── Timing report ──────────────────────────────────────────

    def timing_report(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Generate a timing classification report for a session."""
        session = self.rebuild(session_id)
        if session is None:
            return None

        return {
            "session_id": session_id,
            "total_duration_ms": session.total_duration_ms,
            "node_count": session.node_count,
            "timing_distribution": session.timing_distribution,
            "total_retries": session.total_retries,
            "worker_count": session.worker_count,
            "workers": list(session.unique_workers),
            "steps": [
                {
                    "node": s.node_id,
                    "tool": s.tool,
                    "timing_class": s.timing_class,
                    "duration_ms": s.duration_ms,
                    "worker": s.worker_id,
                    "attempt": s.attempt_number,
                }
                for s in session.steps
            ],
        }

    # ── Ownership timeline ─────────────────────────────────────

    def ownership_timeline(self, session_id: str) -> Optional[List[Dict]]:
        """Return the ownership transition timeline for a session."""
        session = self.rebuild(session_id)
        if session is None:
            return None

        return [
            {
                "event_type": le.event_type.value,
                "task_id": le.task_id,
                "worker_id": le.worker_id,
                "lease_id": le.lease_id,
                "execution_id": le.execution_id,
                "attempt_number": le.attempt_number,
                "timestamp": le.timestamp,
                "duration_ms": le.duration_ms,
            }
            for le in session.ownership_timeline
        ]
