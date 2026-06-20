"""Workflow API Tests.

Verifies DAG serialization, node/edge models, and workflow validation.
Pure model tests — no runtime execution.

Ref: Phase P Batch 2
Ref: Canon LAW 10, LAW 23
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class WorkflowStatus(Enum):
    """Workflow lifecycle status."""

    DRAFT = "draft"
    VALIDATED = "validated"
    SUBMITTED = "submitted"


class NodeType(Enum):
    """Node types in a workflow DAG."""

    ACTION = "action"
    CONDITION = "condition"
    TRIGGER = "trigger"
    OUTPUT = "output"


@dataclass(frozen=True)
class WorkflowNode:
    """A single node in a workflow DAG."""

    id: str
    label: str
    node_type: NodeType = NodeType.ACTION
    x: int = 0
    y: int = 0


@dataclass(frozen=True)
class WorkflowEdge:
    """A directed edge connecting two nodes."""

    id: str
    source: str
    target: str


@dataclass(frozen=True)
class Workflow:
    """Complete workflow definition."""

    id: str
    name: str
    nodes: List[WorkflowNode] = field(default_factory=list)
    edges: List[WorkflowEdge] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.DRAFT


def validate_dag(workflow: Workflow) -> bool:
    """Validate that the workflow graph is a DAG (no cycles, all deps exist)."""
    step_ids = {n.id for n in workflow.nodes}
    for edge in workflow.edges:
        if edge.source not in step_ids or edge.target not in step_ids:
            return False
    visited: set = set()
    in_stack: set = set()

    def _has_cycle(node: str, graph: dict) -> bool:
        visited.add(node)
        in_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if _has_cycle(neighbor, graph):
                    return True
            elif neighbor in in_stack:
                return True
        in_stack.discard(node)
        return False

    graph = {e.source: [e.target] for e in workflow.edges}
    for node_id in step_ids:
        if node_id not in visited:
            if _has_cycle(node_id, graph):
                return False
    return True


def serialize_workflow(workflow: Workflow) -> str:
    """Serialize workflow to JSON string."""
    data = {
        "id": workflow.id,
        "name": workflow.name,
        "nodes": [{"id": n.id, "label": n.label, "type": n.node_type.value, "x": n.x, "y": n.y} for n in workflow.nodes],
        "edges": [{"id": e.id, "source": e.source, "target": e.target} for e in workflow.edges],
        "status": workflow.status.value,
    }
    return json.dumps(data)


def deserialize_workflow(json_str: str) -> Workflow:
    """Deserialize workflow from JSON string."""
    data = json.loads(json_str)
    nodes = [WorkflowNode(id=n["id"], label=n["label"], node_type=NodeType(n["type"]), x=n["x"], y=n["y"]) for n in data["nodes"]]
    edges = [WorkflowEdge(id=e["id"], source=e["source"], target=e["target"]) for e in data["edges"]]
    return Workflow(id=data["id"], name=data["name"], nodes=nodes, edges=edges, status=WorkflowStatus(data["status"]))


class TestWorkflowModels:
    def test_create_valid_workflow(self) -> None:
        wf = Workflow(
            id="wf-1",
            name="Test Workflow",
            nodes=[
                WorkflowNode(id="n1", label="Start", node_type=NodeType.TRIGGER),
                WorkflowNode(id="n2", label="Process", node_type=NodeType.ACTION),
                WorkflowNode(id="n3", label="End", node_type=NodeType.OUTPUT),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n3"),
            ],
        )
        assert len(wf.nodes) == 3
        assert len(wf.edges) == 2
        assert wf.status == WorkflowStatus.DRAFT

    def test_validate_dag_no_cycles(self) -> None:
        wf = Workflow(
            id="wf-2",
            name="Valid DAG",
            nodes=[
                WorkflowNode(id="n1", label="A"),
                WorkflowNode(id="n2", label="B"),
                WorkflowNode(id="n3", label="C"),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n3"),
            ],
        )
        assert validate_dag(wf) is True

    def test_validate_dag_rejects_cycles(self) -> None:
        wf = Workflow(
            id="wf-3",
            name="Cyclic DAG",
            nodes=[
                WorkflowNode(id="n1", label="A"),
                WorkflowNode(id="n2", label="B"),
            ],
            edges=[
                WorkflowEdge(id="e1", source="n1", target="n2"),
                WorkflowEdge(id="e2", source="n2", target="n1"),
            ],
        )
        assert validate_dag(wf) is False

    def test_serialize_roundtrip(self) -> None:
        wf = Workflow(
            id="wf-4",
            name="Roundtrip Test",
            nodes=[WorkflowNode(id="n1", label="Step 1", node_type=NodeType.ACTION)],
            edges=[],
        )
        json_str = serialize_workflow(wf)
        restored = deserialize_workflow(json_str)
        assert restored.id == wf.id
        assert restored.name == wf.name
        assert len(restored.nodes) == 1
        assert restored.nodes[0].label == "Step 1"

    def test_validate_dag_rejects_missing_edges(self) -> None:
        wf = Workflow(
            id="wf-5",
            name="Missing Edge Target",
            nodes=[WorkflowNode(id="n1", label="A")],
            edges=[WorkflowEdge(id="e1", source="n1", target="nonexistent")],
        )
        assert validate_dag(wf) is False
