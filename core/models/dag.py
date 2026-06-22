from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ── Version ──────────────────────────────────────────────────────
DAG_SCHEMA_VERSION = "1.0.0"


# ── State Machine ────────────────────────────────────────────────
class NodeState(str, Enum):
    PENDING = "pending"
    PLANNED = "planned"
    RUNNING = "running"
    WAITING = "waiting"
    FAILED = "failed"
    RETRYING = "retrying"
    ROLLED_BACK = "rolled_back"
    COMPLETED = "completed"

    def can_transition_to(self, target: NodeState) -> bool:
        transitions = {
            NodeState.PENDING:    {NodeState.PLANNED},
            NodeState.PLANNED:    {NodeState.RUNNING, NodeState.WAITING},
            NodeState.RUNNING:    {NodeState.COMPLETED, NodeState.FAILED, NodeState.WAITING},
            NodeState.WAITING:    {NodeState.RUNNING, NodeState.FAILED},
            NodeState.FAILED:     {NodeState.RETRYING, NodeState.ROLLED_BACK, NodeState.PLANNED},
            NodeState.RETRYING:   {NodeState.RUNNING, NodeState.FAILED},
            NodeState.ROLLED_BACK: set(),
            NodeState.COMPLETED:   set(),
        }
        return target in transitions.get(self, set())


# ── Configuration ────────────────────────────────────────────────
@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_seconds: float = 2.0
    max_backoff_seconds: float = 60.0


@dataclass
class RollbackStrategy:
    strategy_type: str = "compensating_tool"
    compensating_tool: Optional[str] = None


@dataclass
class ToolSpec:
    name: str = ""
    description: str = ""
    inputs: Dict[str, str] = field(default_factory=dict)
    outputs: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    rollback_strategy: RollbackStrategy = field(default_factory=RollbackStrategy)
    contract: Optional[Any] = None


@dataclass
class NodeConfig:
    timeout_seconds: float = 30.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    rollback_strategy: RollbackStrategy = field(default_factory=RollbackStrategy)


# ── DAG Nodes & Edges ────────────────────────────────────────────
@dataclass
class PlanNode:
    id: str = ""
    tool: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    config: NodeConfig = field(default_factory=NodeConfig)
    state: NodeState = NodeState.PENDING
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    result: Optional[Dict[str, Any]] = None


@dataclass
class PlanEdge:
    source_id: str = ""
    target_id: str = ""
    condition: str = "success"


# ── Dependency Graph (domain operations only) ────────────────────
class DependencyGraph:
    """A DAG of PlanNodes connected by PlanEdges."""
    nodes: Dict[str, PlanNode]
    edges: List[PlanEdge]
    version: str

    def __init__(self, version: str = DAG_SCHEMA_VERSION) -> None:
        self.nodes = {}
        self.edges = []
        self.version = version

    def add_node(self, node: PlanNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, source_id: str, target_id: str,
                 condition: str = "success") -> None:
        self.edges.append(PlanEdge(source_id, target_id, condition))

    def predecessors(self, node_id: str) -> List[PlanNode]:
        sources = {e.source_id for e in self.edges
                   if e.target_id == node_id}
        return [self.nodes[s] for s in sources if s in self.nodes]

    def successors(self, node_id: str) -> List[PlanNode]:
        targets = {e.target_id for e in self.edges
                   if e.source_id == node_id}
        return [self.nodes[t] for t in targets if t in self.nodes]

    def entry_nodes(self) -> List[PlanNode]:
        has_incoming = {e.target_id for e in self.edges}
        return [n for nid, n in self.nodes.items()
                if nid not in has_incoming]

    def leaf_nodes(self) -> List[PlanNode]:
        has_outgoing = {e.source_id for e in self.edges}
        return [n for nid, n in self.nodes.items()
                if nid not in has_outgoing]

    def topo_sort(self) -> List[PlanNode]:
        from core.dag_utils import topo_sort as _topo_sort
        return _topo_sort(self)

    def independent_branches(self) -> List[List[PlanNode]]:
        from core.dag_utils import independent_branches as _branches
        return _branches(self)

    def validate(self) -> List[str]:
        from core.dag_utils import validate as _validate
        return _validate(self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "nodes": {
                nid: {
                    "id": n.id, "tool": n.tool,
                    "state": n.state.value,
                    "inputs": n.inputs,
                    "retry_count": n.retry_count,
                    "error": n.error,
                }
                for nid, n in self.nodes.items()
            },
            "edges": [
                {"source": e.source_id, "target": e.target_id,
                 "condition": e.condition}
                for e in self.edges
            ],
        }
