"""Consolidated Replay Engine — single replay truth.

Merges DAGReplayEngine and DistributedReplayEngine into one hierarchy.
DAGReplayEngine → ReplayEngine (base implementation)
DistributedReplayEngine → ReplayEngine.rebuild_distributed() (extended)
"""

from __future__ import annotations

import copy
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.replay.engine")


# ── Shared Data Types ──────────────────────────────────────────

@dataclass
class ReplayStep:
    node_id: str = ""
    tool: str = ""
    state: str = ""
    duration_ms: float = 0.0
    error: Optional[str] = None
    worker_id: Optional[str] = None
    timing_class: Optional[str] = None
    lease_events: List[Dict[str, Any]] = field(default_factory=list)
    execution_id: Optional[str] = None
    attempt_number: int = 1


@dataclass
class ReplaySession:
    session_id: str = ""
    dag_id: str = ""
    status: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    total_duration_ms: float = 0.0
    node_count: int = 0
    steps: List[ReplayStep] = field(default_factory=list)
    worker_count: int = 0
    unique_workers: List[str] = field(default_factory=list)
    total_retries: int = 0
    timing_distribution: Dict[str, int] = field(default_factory=dict)
    ownership_timeline: List[Dict[str, Any]] = field(default_factory=list)
    error_count: int = 0


# ── Replay Engine ──────────────────────────────────────────────

class ReplayEngine:
    """Unified replay engine for DAG execution traces.

    Replaces both DAGReplayEngine and DistributedReplayEngine.
    Provides:
      - rebuild(session_id) — standard DAG replay
      - rebuild_distributed(session_id) — extended with distributed context
      - available_sessions() — list replayable sessions
      - compare(a, b) — diff two sessions
    """

    def __init__(self, memory: Any):
        self._memory = memory

    def available_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List sessions with available DAG traces."""
        if hasattr(self._memory, "get_dag_trace"):
            sessions = []
            for sid in self._memory.list_sessions(limit=limit):
                trace = self._memory.get_dag_trace(sid)
                if trace:
                    sessions.append({
                        "session_id": sid,
                        "dag_id": trace.get("dag_id", ""),
                        "status": trace.get("status", ""),
                        "node_count": len(trace.get("nodes", [])),
                        "started_at": trace.get("started_at", 0),
                        "completed_at": trace.get("completed_at", 0),
                        "has_distributed": "distributed" in trace,
                    })
            return sessions
        return []

    def rebuild(self, session_id: str) -> Optional[ReplaySession]:
        """Rebuild a DAG execution session from stored trace.

        Args:
            session_id: The session to rebuild.

        Returns:
            ReplaySession with all steps, or None if trace not found.
        """
        trace = self._get_trace(session_id)
        if not trace:
            return None

        session = self._build_base_session(session_id, trace)
        nodes = trace.get("nodes", [])
        edges = trace.get("edges", [])
        node_map = {n["id"]: n for n in nodes}
        node_results = trace.get("node_results", {})

        # Topological sort
        sorted_nodes = self._topo_sort(nodes, edges)

        for node_id in sorted_nodes:
            node_data = node_map.get(node_id, {})
            result = node_results.get(node_id, {})
            step = ReplayStep(
                node_id=node_id,
                tool=node_data.get("tool", ""),
                state=node_data.get("state", result.get("status", "unknown")),
                duration_ms=result.get("duration_ms", 0.0),
                error=result.get("error"),
            )
            session.steps.append(step)

        session.total_duration_ms = sum(s.duration_ms for s in session.steps)
        session.error_count = sum(1 for s in session.steps if s.error)
        return session

    def rebuild_distributed(self, session_id: str) -> Optional[ReplaySession]:
        """Rebuild with distributed execution context.

        Extends rebuild() with worker assignments, lease events,
        timing classes, and retry tracking.
        """
        trace = self._get_trace(session_id)
        if not trace:
            return None

        session = self._build_base_session(session_id, trace)
        nodes = trace.get("nodes", [])
        edges = trace.get("edges", [])
        node_map = {n["id"]: n for n in nodes}
        node_results = trace.get("node_results", {})
        distributed = trace.get("distributed", {})

        # Distributed metadata
        lease_events = distributed.get("lease_events", [])
        timing_classes = distributed.get("timing_classes", {})

        sorted_nodes = self._topo_sort(nodes, edges)
        workers_seen: set[str] = set()

        for node_id in sorted_nodes:
            node_data = node_map.get(node_id, {})
            result = node_results.get(node_id, {})
            worker_id = result.get("worker_id", distributed.get("worker_id", ""))
            if worker_id:
                workers_seen.add(worker_id)

            step = ReplayStep(
                node_id=node_id,
                tool=node_data.get("tool", ""),
                state=node_data.get("state", result.get("status", "unknown")),
                duration_ms=result.get("duration_ms", 0.0),
                error=result.get("error"),
                worker_id=worker_id,
                timing_class=timing_classes.get(node_id),
                lease_events=[
                    e for e in lease_events
                    if e.get("node_id") == node_id
                ],
                execution_id=distributed.get("execution_id", ""),
                attempt_number=result.get("attempt_number", 1),
            )
            session.steps.append(step)

        session.total_duration_ms = sum(s.duration_ms for s in session.steps)
        session.error_count = sum(1 for s in session.steps if s.error)
        session.worker_count = len(workers_seen)
        session.unique_workers = list(workers_seen)

        # Timing distribution
        for step in session.steps:
            tc = step.timing_class or "unknown"
            session.timing_distribution[tc] = session.timing_distribution.get(tc, 0) + 1

        # Ownership timeline
        for ev in lease_events:
            session.ownership_timeline.append({
                "node_id": ev.get("node_id"),
                "worker_id": ev.get("worker_id"),
                "event": ev.get("event", "leased"),
                "timestamp": ev.get("timestamp", 0),
            })

        return session

    def compare(self, session_a: str, session_b: str) -> Dict[str, Any]:
        """Compare two replay sessions."""
        a = self.rebuild(session_a)
        b = self.rebuild(session_b)
        if not a or not b:
            return {"error": "One or both sessions not found"}

        diffs = []
        max_steps = max(len(a.steps), len(b.steps))
        for i in range(max_steps):
            step_a = a.steps[i] if i < len(a.steps) else None
            step_b = b.steps[i] if i < len(b.steps) else None
            if step_a and step_b:
                if step_a.state != step_b.state or step_a.duration_ms != step_b.duration_ms:
                    diffs.append({
                        "node_id": step_a.node_id,
                        "a_state": step_a.state, "b_state": step_b.state,
                        "a_duration": step_a.duration_ms, "b_duration": step_b.duration_ms,
                    })

        return {
            "a_id": session_a,
            "b_id": session_b,
            "a_node_count": a.node_count,
            "b_node_count": b.node_count,
            "a_duration": a.total_duration_ms,
            "b_duration": b.total_duration_ms,
            "a_errors": a.error_count,
            "b_errors": b.error_count,
            "differences": len(diffs),
            "diff_details": diffs[:20],
        }

    def _get_trace(self, session_id: str) -> Optional[Dict[str, Any]]:
        if hasattr(self._memory, "get_dag_trace"):
            return self._memory.get_dag_trace(session_id)
        if hasattr(self._memory, "get_session"):
            sess = self._memory.get_session(session_id)
            if sess and hasattr(sess, "dag_trace"):
                return sess.dag_trace
        return None

    def _build_base_session(self, session_id: str,
                            trace: Dict[str, Any]) -> ReplaySession:
        nodes = trace.get("nodes", [])
        return ReplaySession(
            session_id=session_id,
            dag_id=trace.get("dag_id", ""),
            status=trace.get("status", ""),
            started_at=trace.get("started_at", 0.0),
            completed_at=trace.get("completed_at", 0.0),
            node_count=len(nodes),
        )

    @staticmethod
    def _topo_sort(nodes: List[Dict[str, Any]],
                   edges: List[Dict[str, Any]]) -> List[str]:
        """Topological sort of nodes by dependency edges."""
        in_degree: Dict[str, int] = {n["id"]: 0 for n in nodes}
        adj: Dict[str, List[str]] = {n["id"]: [] for n in nodes}

        for edge in edges:
            src = edge.get("source", edge.get("source_id", ""))
            tgt = edge.get("target", edge.get("target_id", ""))
            if src in adj and tgt in in_degree:
                adj[src].append(tgt)
                in_degree[tgt] = in_degree.get(tgt, 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        sorted_nodes = []

        while queue:
            nid = queue.pop(0)
            sorted_nodes.append(nid)
            for neighbor in adj.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return sorted_nodes


# ── Query Replay Engine ────────────────────────────────────────

@dataclass
class QueryLog:
    query_id: str = ""
    query_text: str = ""
    strategy: str = ""
    results: List[Dict[str, Any]] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=dict)
    context: str = ""
    feedback: float = 0.0
    timestamp: float = 0.0


class QueryReplayEngine:
    """Replay engine for query logs (from query_replay.py).

    Logs queries and their results for self-tuning analysis.
    INDEPENDENT from DAG replay — different data, different purpose.
    """

    def __init__(self, db_path: str = ""):
        self._db_path = db_path
        self._logs: List[QueryLog] = []

    def log(self, query: str, strategy: str, results: List[Dict[str, Any]],
            weights: Optional[Dict[str, float]] = None,
            context: str = "") -> str:
        query_id = f"q-{len(self._logs) + 1}-{int(time.time())}"
        self._logs.append(QueryLog(
            query_id=query_id,
            query_text=query,
            strategy=strategy,
            results=results,
            weights=weights or {},
            context=context,
            timestamp=time.time(),
        ))
        return query_id

    def get_log(self, query_id: str) -> Optional[QueryLog]:
        for log in self._logs:
            if log.query_id == query_id:
                return log
        return None

    def recent(self, limit: int = 20) -> List[QueryLog]:
        return sorted(self._logs, key=lambda l: l.timestamp, reverse=True)[:limit]

    def find_similar(self, query_text: str) -> List[QueryLog]:
        query_lower = query_text.lower()
        return [l for l in self._logs if query_lower in l.query_text.lower()]

    def compare_runs(self, query_text: str) -> Dict[str, Any]:
        matching = self.find_similar(query_text)
        if len(matching) < 2:
            return {"error": "Need at least 2 matching runs"}
        a, b = matching[-2], matching[-1]
        return {
            "query": query_text,
            "run_a": {"timestamp": a.timestamp, "results": len(a.results), "strategy": a.strategy},
            "run_b": {"timestamp": b.timestamp, "results": len(b.results), "strategy": b.strategy},
            "weight_deltas": {
                k: round(b.weights.get(k, 0) - a.weights.get(k, 0), 3)
                for k in set(list(a.weights.keys()) + list(b.weights.keys()))
            },
        }

    def update_feedback(self, query_id: str, feedback: float) -> bool:
        log = self.get_log(query_id)
        if log:
            log.feedback = feedback
            return True
        return False

    def import_logs(self, logs: List[QueryLog]) -> int:
        self._logs.extend(logs)
        return len(logs)
