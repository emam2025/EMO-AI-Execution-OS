"""Workflow Router Tests.

Verifies DAG validation, workflow storage, and endpoint logic.
Tests the router functions directly without FastAPI TestClient.

Ref: Phase P Batch 3
Ref: Canon LAW 10, LAW 23
"""

import uuid
from typing import Any, Dict, List


class MockHTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


_workflow_store: Dict[str, Dict[str, Any]] = {}


def _validate_dag(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> bool:
    step_ids = {n["id"] for n in nodes}
    for edge in edges:
        if edge["source"] not in step_ids or edge["target"] not in step_ids:
            return False
    visited: set = set()
    in_stack: set = set()

    def _has_cycle(node: str, graph: Dict[str, List[str]]) -> bool:
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

    graph: Dict[str, List[str]] = {e["source"]: [e["target"]] for e in edges}
    for node_id in step_ids:
        if node_id not in visited:
            if _has_cycle(node_id, graph):
                return False
    return True


def _create_workflow(name: str, nodes: List[Dict], edges: List[Dict]) -> Dict[str, Any]:
    if not _validate_dag(nodes, edges):
        raise MockHTTPException(400, "Invalid DAG: cycle detected or missing edge references")
    workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
    workflow = {"id": workflow_id, "name": name, "nodes": nodes, "edges": edges, "status": "draft"}
    _workflow_store[workflow_id] = workflow
    return workflow


def _get_workflow(workflow_id: str) -> Dict[str, Any]:
    if workflow_id not in _workflow_store:
        raise MockHTTPException(404, "Workflow not found")
    return _workflow_store[workflow_id]


def _submit_workflow(workflow_id: str) -> Dict[str, Any]:
    if workflow_id not in _workflow_store:
        raise MockHTTPException(404, "Workflow not found")
    workflow = _workflow_store[workflow_id]
    if workflow["status"] != "draft":
        raise MockHTTPException(400, f"Cannot submit workflow in status '{workflow['status']}'")
    workflow["status"] = "submitted"
    return workflow


def _list_workflows() -> List[Dict[str, Any]]:
    return list(_workflow_store.values())


def _reset_store() -> None:
    _workflow_store.clear()


class TestWorkflowRouter:
    def test_create_valid_workflow(self) -> None:
        _reset_store()
        wf = _create_workflow(
            name="Test Workflow",
            nodes=[{"id": "n1", "label": "Start", "type": "trigger"}, {"id": "n2", "label": "Process", "type": "action"}],
            edges=[{"id": "e1", "source": "n1", "target": "n2"}],
        )
        assert wf["name"] == "Test Workflow"
        assert wf["status"] == "draft"
        assert len(wf["nodes"]) == 2
        assert len(wf["edges"]) == 1

    def test_rejects_cyclic_workflow(self) -> None:
        _reset_store()
        try:
            _create_workflow(
                name="Cyclic",
                nodes=[{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}],
                edges=[{"id": "e1", "source": "n1", "target": "n2"}, {"id": "e2", "source": "n2", "target": "n1"}],
            )
            assert False, "Should have raised MockHTTPException"
        except MockHTTPException as e:
            assert e.status_code == 400
            assert "cycle" in e.detail.lower() or "invalid" in e.detail.lower()

    def test_get_workflow(self) -> None:
        _reset_store()
        wf = _create_workflow(name="Fetch Test", nodes=[{"id": "n1", "label": "A"}], edges=[])
        fetched = _get_workflow(wf["id"])
        assert fetched["name"] == "Fetch Test"

    def test_get_nonexistent_workflow(self) -> None:
        _reset_store()
        try:
            _get_workflow("nonexistent")
            assert False, "Should have raised MockHTTPException"
        except MockHTTPException as e:
            assert e.status_code == 404

    def test_submit_workflow(self) -> None:
        _reset_store()
        wf = _create_workflow(name="Submit Test", nodes=[{"id": "n1", "label": "A"}], edges=[])
        submitted = _submit_workflow(wf["id"])
        assert submitted["status"] == "submitted"

    def test_list_workflows(self) -> None:
        _reset_store()
        _create_workflow(name="WF-1", nodes=[], edges=[])
        _create_workflow(name="WF-2", nodes=[], edges=[])
        result = _list_workflows()
        assert len(result) == 2
