"""DAG Replay Engine — Time Travel for AI Code Intelligence.

Reconstructs, visualises, and compares past DAG executions from stored
traces in ExecutionMemory.

Architecture:
    ExecutionMemory (dag_trace) → DAGReplayEngine
        → ReplaySession (step-by-step)
        → visualize() (ASCII DAG)
        → compare() (side-by-side diff)

Usage:
    replay = DAGReplayEngine(memory)
    for session in replay.available_sessions():
        print(replay.visualize(session.session_id))
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .execution_memory import ExecutionMemory
from .models.dag import (
    DependencyGraph, PlanNode, PlanEdge, NodeState,
)


# ======================================================================
# Data types
# ======================================================================

@dataclass
class ReplayStep:
    """A single node execution step in a replay."""
    node_id: str
    tool: str
    inputs: Dict[str, Any]
    state: str
    duration_ms: float
    retry_count: int
    error: Optional[str]
    output_summary: str


@dataclass
class ReplaySession:
    """Reconstructed execution for one session."""
    session_id: str
    query: str
    strategy: str
    status: str
    started_at: float
    completed_at: Optional[float]
    total_duration_ms: float
    node_count: int
    edge_count: int
    steps: List[ReplayStep]  # topological order
    graph: DependencyGraph
    raw_trace: Dict[str, Any]


@dataclass
class RunComparison:
    """Difference between two session executions."""
    session_a: str
    session_b: str
    query_a: str
    query_b: str
    total_duration_delta_ms: float
    node_count_delta: int
    status_match: bool
    tool_diff: List[str]
    node_comparisons: List[Dict[str, Any]]


# ======================================================================
# DAG Replay Engine
# ======================================================================

class DAGReplayEngine:
    """Replays, visualizes, and compares DAG executions.

    Usage:
        replay = DAGReplayEngine(execution_memory)
        for s in replay.available_sessions():
            print(replay.visualize(s["session_id"]))
    """

    def __init__(self, memory: ExecutionMemory):
        self.memory = memory

    # ── session listing ──────────────────────────────────────────────

    def available_sessions(
        self, limit: int = 20, has_trace: bool = True,
    ) -> List[Dict[str, Any]]:
        """List sessions with (optionally) DAG traces available."""
        sessions = self.memory.recent_sessions(limit=limit)
        result = []
        for s in sessions:
            if has_trace:
                trace = self.memory.get_dag_trace(s.session_id)
                if trace is None:
                    continue
            entry = {
                "session_id": s.session_id,
                "query": s.query,
                "strategy": s.strategy,
                "status": s.status,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
            }
            if has_trace and trace:
                entry["node_count"] = len(trace.get("nodes", {}))
                entry["edge_count"] = len(trace.get("edges", []))
            result.append(entry)
        return result

    # ── replay reconstruction ────────────────────────────────────────

    def rebuild(self, session_id: str) -> Optional[ReplaySession]:
        """Rebuild a full ReplaySession from a stored DAG trace."""
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
                edata["source_id"], edata["target_id"],
                edata.get("condition", "success"),
            )

        # Build topological steps
        steps: List[ReplayStep] = []
        try:
            topo = dag.topo_sort()
        except ValueError:
            topo = list(dag.nodes.values())

        for node in topo:
            dur = 0.0
            if node.started_at and node.completed_at:
                dur = (node.completed_at - node.started_at) * 1000
            steps.append(ReplayStep(
                node_id=node.id,
                tool=node.tool,
                inputs=node.inputs,
                state=node.state.value,
                duration_ms=round(dur, 1),
                retry_count=node.retry_count,
                error=node.error,
                output_summary=_summarize(node.result),
            ))

        total_dur = 0.0
        if sess.started_at and sess.completed_at:
            total_dur = (sess.completed_at - sess.started_at) * 1000

        # Prefer trace status (more granular) over session status
        trace_status = trace.get("status", sess.status)

        return ReplaySession(
            session_id=sess.session_id,
            query=sess.query,
            strategy=sess.strategy,
            status=trace_status,
            started_at=sess.started_at,
            completed_at=sess.completed_at,
            total_duration_ms=round(total_dur, 1),
            node_count=len(dag.nodes),
            edge_count=len(dag.edges),
            steps=steps,
            graph=dag,
            raw_trace=trace,
        )

    # ── step-by-step ─────────────────────────────────────────────────

    def step_through(
        self, session_id: str,
    ) -> List[Dict[str, Any]]:
        """Return a chronological narrative of the execution."""
        replay = self.rebuild(session_id)
        if replay is None:
            return [{"error": f"Session {session_id} not found or has no trace"}]

        narrative = []
        narrative.append({
            "time": "START",
            "query": replay.query,
            "strategy": replay.strategy,
            "total_nodes": replay.node_count,
            "total_edges": replay.edge_count,
        })

        for step in replay.steps:
            entry: Dict[str, Any] = {
                "step": step.node_id,
                "tool": step.tool,
                "state": step.state,
                "duration_ms": step.duration_ms,
                "retries": step.retry_count,
            }
            if step.error:
                entry["error"] = step.error
            if step.inputs:
                entry["inputs"] = step.inputs
            if step.output_summary:
                entry["output"] = step.output_summary
            narrative.append(entry)

        narrative.append({
            "time": "END",
            "status": replay.status,
            "total_duration_ms": replay.total_duration_ms,
        })
        return narrative

    # ── visualization ────────────────────────────────────────────────

    def visualize(self, session_id: str) -> str:
        """Render the DAG as an ASCII graph."""
        replay = self.rebuild(session_id)
        if replay is None:
            return f"[No trace for session {session_id}]"

        lines: List[str] = []
        lines.append(f"╔══ DAG Execution: {replay.query} ═══")
        lines.append(f"║ Session: {replay.session_id[:8]}…")
        lines.append(f"║ Status: {replay.status}")
        lines.append(f"║ Duration: {replay.total_duration_ms}ms")
        lines.append(f"║ Strategy: {replay.strategy}")
        lines.append(f"║ Nodes: {replay.node_count}  Edges: {replay.edge_count}")
        lines.append("║")

        # Group by topological level
        try:
            topo = replay.graph.topo_sort()
        except ValueError:
            topo = list(replay.graph.nodes.values())

        depth: Dict[str, int] = {}
        for node in topo:
            preds = replay.graph.predecessors(node.id)
            depth[node.id] = max((depth.get(p.id, 0) for p in preds), default=0) + 1

        levels: Dict[int, List[PlanNode]] = {}
        for node in topo:
            levels.setdefault(depth[node.id], []).append(node)

        for level_num in sorted(levels):
            nodes_at_level = levels[level_num]
            line_parts = [f"║  L{level_num}"]
            for node in nodes_at_level:
                icon = _state_icon(node.state)
                dur = ""
                if node.started_at and node.completed_at:
                    dur = f" {int((node.completed_at - node.started_at) * 1000)}ms"
                error_mark = " ✗" if node.error else ""
                line_parts.append(
                    f"  {icon} {node.id}({_short_tool(node.tool)}){dur}{error_mark}"
                )
            lines.append("   ".join(line_parts))

        # Draw edges
        if replay.edge_count > 0:
            lines.append("║")
            lines.append("║  Edges:")
            for e in replay.raw_trace.get("edges", []):
                cond = f" [{e.get('condition', 'success')}]" if e.get("condition", "success") != "success" else ""
                lines.append(f"║    {e['source_id']} → {e['target_id']}{cond}")

        lines.append("╚══")
        return "\n".join(lines)

    # ── run comparison ───────────────────────────────────────────────

    def compare(self, session_a: str, session_b: str) -> RunComparison:
        """Compare two DAG executions side-by-side."""
        ra = self.rebuild(session_a)
        rb = self.rebuild(session_b)

        if ra is None and rb is None:
            raise LookupError(f"Neither {session_a} nor {session_b} found")
        if ra is None:
            raise LookupError(f"Session {session_a} not found")
        if rb is None:
            raise LookupError(f"Session {session_b} not found")

        dur_delta = rb.total_duration_ms - ra.total_duration_ms
        node_delta = rb.node_count - ra.node_count
        status_match = ra.status == rb.status

        # Tool diff: tools in B not in A
        tools_a = {s.tool for s in ra.steps}
        tools_b = {s.tool for s in rb.steps}
        added = tools_b - tools_a
        removed = tools_a - tools_b
        tool_diff = [f"+{t}" for t in sorted(added)] + [f"-{t}" for t in sorted(removed)]

        # Per-node comparisons
        node_compares: List[Dict[str, Any]] = []
        for step_a, step_b in zip(ra.steps, rb.steps):
            same_tool = step_a.tool == step_b.tool
            same_state = step_a.state == step_b.state
            dur_diff = round(step_b.duration_ms - step_a.duration_ms, 1)
            node_compares.append({
                "node_id_a": step_a.node_id,
                "node_id_b": step_b.node_id,
                "tool_match": same_tool,
                "state_match": same_state,
                "duration_delta_ms": dur_diff,
                "error_a": step_a.error,
                "error_b": step_b.error,
            })

        return RunComparison(
            session_a=session_a,
            session_b=session_b,
            query_a=ra.query,
            query_b=rb.query,
            total_duration_delta_ms=round(dur_delta, 1),
            node_count_delta=node_delta,
            status_match=status_match,
            tool_diff=tool_diff,
            node_comparisons=node_compares,
        )


# ======================================================================
# Helpers
# ======================================================================

def _state_icon(state: NodeState) -> str:
    icons = {
        NodeState.COMPLETED: "✓",
        NodeState.FAILED: "✗",
        NodeState.RUNNING: "●",
        NodeState.PENDING: "○",
        NodeState.PLANNED: "◉",
        NodeState.RETRYING: "↻",
        NodeState.ROLLED_BACK: "⊘",
        NodeState.WAITING: "◌",
    }
    return icons.get(state, "?")


def _short_tool(tool_name: str) -> str:
    """Shorten a dotted tool name for display."""
    parts = tool_name.rsplit(".", 1)
    return parts[-1] if len(parts) > 1 else tool_name


def _summarize(result: Any, max_len: int = 120) -> str:
    if result is None:
        return ""
    text = json.dumps(result, default=str)
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text
