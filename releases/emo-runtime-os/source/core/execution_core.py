"""ExecutionCore — pure logic layer, zero IO, zero side effects.

Responsibilities:
  - DAG schema version validation
  - Topological/traversal queries (successor collection)
  - State transition validation + event type mapping
  - Retry/backoff computation
  - Failure pattern analysis
  - Default tool runner (mock, deterministic)
  - DAG builder helper

Rules:
  - No threading, no file IO, no network, no event bus, no memory.
  - Every method is either @staticmethod or operates only on provided data.
  - Deterministic: same inputs → same outputs, always.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from . import dag_utils
from .models.dag import (
    DependencyGraph,
    NodeState,
    PlanNode,
    PlanEdge,
    ToolSpec,
)
from .contracts import SUPPORTED_SCHEMA_VERSIONS, SchemaVersionMismatch

logger = logging.getLogger("emo_ai.execution_core")


# ═══════════════════════════════════════════════════════════════════════
# Failure Intelligence (pure analysis, thread-safe via lock)
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class FailurePattern:
    tool: str = ""
    strategy: str = ""
    failure_count: int = 0
    total_count: int = 0
    failure_rate: float = 0.0


class FailureIntelligence:
    def __init__(self):
        self._lock = threading.Lock()
        self._stats: Dict[Tuple[str, str], Tuple[int, int]] = {}

    def record_result(self, tool: str, strategy: str, success: bool) -> None:
        with self._lock:
            key = (tool, strategy)
            failures, total = self._stats.get(key, (0, 0))
            total += 1
            if not success:
                failures += 1
            self._stats[key] = (failures, total)

    def failure_rate(self, tool: str, strategy: str) -> float:
        failures, total = self._stats.get((tool, strategy), (0, 0))
        return failures / total if total > 0 else 0.0

    def top_patterns(self, limit: int = 10) -> List[FailurePattern]:
        patterns = [
            FailurePattern(
                tool=t, strategy=s,
                failure_count=f, total_count=tot,
                failure_rate=f / tot,
            )
            for (t, s), (f, tot) in self._stats.items()
        ]
        patterns.sort(key=lambda p: p.failure_rate, reverse=True)
        return patterns[:limit]

    def suggest_alternative(self, tool: str, strategy: str) -> Optional[str]:
        rate = self.failure_rate(tool, strategy)
        if rate < 0.3:
            return None
        best_rate = 1.0
        best_strategy: Optional[str] = None
        for (t, s), (f, tot) in self._stats.items():
            if t == tool and s != strategy and tot >= 3:
                r = f / tot
                if r < best_rate:
                    best_rate = r
                    best_strategy = s
        return best_strategy if best_rate < rate else None

    def report(self) -> Dict[str, Any]:
        return {
            "patterns": [
                {"tool": p.tool, "strategy": p.strategy,
                 "failure_rate": p.failure_rate,
                 "count": p.total_count}
                for p in self.top_patterns(20)
            ],
            "total_correlations": len(self._stats),
        }


# ═══════════════════════════════════════════════════════════════════════
# ExecutionCore — pure execution logic
# ═══════════════════════════════════════════════════════════════════════


class ExecutionCore:
    """Deterministic execution logic — no IO, no side effects."""

    # ── State transition event mapping (pure) ──

    STATE_EVENT_MAP: Dict[Tuple[NodeState, NodeState], str] = {
        (NodeState.PLANNED, NodeState.RUNNING): "NODE_STARTED",
        (NodeState.RUNNING, NodeState.COMPLETED): "NODE_COMPLETED",
        (NodeState.RUNNING, NodeState.FAILED): "NODE_FAILED",
        (NodeState.PLANNED, NodeState.FAILED): "NODE_FAILED",
        (NodeState.FAILED, NodeState.RETRYING): "RETRY_DECISION",
        (NodeState.RETRYING, NodeState.RUNNING): "NODE_STARTED",
        (NodeState.COMPLETED, NodeState.ROLLED_BACK): "STATE_TRANSITION",
        (NodeState.FAILED, NodeState.ROLLED_BACK): "STATE_TRANSITION",
        (NodeState.RUNNING, NodeState.PENDING): "STATE_TRANSITION",
    }

    @staticmethod
    def get_event_type_for_transition(
        old: NodeState, new: NodeState,
    ) -> str:
        return ExecutionCore.STATE_EVENT_MAP.get(
            (old, new), "STATE_TRANSITION",
        )

    @staticmethod
    def validate_transition(node: PlanNode, target: NodeState) -> bool:
        return node.state.can_transition_to(target)

    # ── Schema version ──

    @staticmethod
    def check_schema_version(dag: DependencyGraph) -> None:
        if dag.version not in SUPPORTED_SCHEMA_VERSIONS:
            raise SchemaVersionMismatch(dag.version, SUPPORTED_SCHEMA_VERSIONS)

    # ── DAG algorithms (delegated to dag_utils) ──

    @staticmethod
    def topo_sort(dag: DependencyGraph) -> List[PlanNode]:
        return dag_utils.topo_sort(dag)

    @staticmethod
    def independent_branches(dag: DependencyGraph) -> List[List[PlanNode]]:
        return dag_utils.independent_branches(dag)

    @staticmethod
    def validate_dag(dag: DependencyGraph) -> List[str]:
        return dag_utils.validate(dag)

    # ── Topological queries ──

    @staticmethod
    def collect_successors(node_id: str, dag: DependencyGraph) -> List[str]:
        visited: Set[str] = set()
        queue = deque([node_id])
        while queue:
            current = queue.popleft()
            for edge in dag.edges:
                if edge.source_id == current and edge.target_id not in visited:
                    visited.add(edge.target_id)
                    queue.append(edge.target_id)
        visited.discard(node_id)
        return list(visited)

    # ── Default tool runner (pure mock) ──

    @staticmethod
    def default_tool_runner(node: PlanNode) -> Dict[str, Any]:
        return {"tool": node.tool, "inputs": node.inputs,
                "output": f"executed_{node.tool}"}

    # ── Retry backoff computation (pure, deterministic) ──

    @staticmethod
    def compute_backoff(
        retry_count: int,
        base_seconds: float = 2.0,
        max_seconds: float = 60.0,
    ) -> float:
        return min(
            base_seconds * (2 ** (retry_count - 1)),
            max_seconds,
        )

    # ── Success/failure classification ──

    @staticmethod
    def should_retry(retry_count: int, max_retries: int) -> bool:
        return retry_count < max_retries


# ═══════════════════════════════════════════════════════════════════════
# DAG Builder (pure helper)
# ═══════════════════════════════════════════════════════════════════════


class DAGBuilder:
    def __init__(self):
        self._nodes: Dict[str, PlanNode] = {}
        self._edges: List[PlanEdge] = []

    def add(self, node_id: str, tool: str = "", inputs: Optional[Dict[str, Any]] = None, **kwargs) -> "DAGBuilder":
        node = PlanNode(
            id=node_id, tool=tool,
            inputs=inputs or {},
            **kwargs,
        )
        self._nodes[node_id] = node
        return self

    def depends(self, child_id: str, parent_id: str) -> "DAGBuilder":
        self._edges.append(PlanEdge(source_id=parent_id, target_id=child_id))
        return self

    def build(self) -> DependencyGraph:
        dag = DependencyGraph()
        for nid in sorted(self._nodes):
            dag.add_node(self._nodes[nid])
        for e in self._edges:
            dag.add_edge(e.source_id, e.target_id, e.condition)
        return dag
