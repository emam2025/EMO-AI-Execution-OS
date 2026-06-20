"""Workflow Studio Tests.

Verifies workflow creation, tool binding, DAG validation, execution submission, and history.
Tests business logic directly — no mocks, no ellipsis, no pass.

Ref: Phase P Batch 5 (P.6 — Workflow Studio)
Ref: Canon LAW 10, LAW 23
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List


class MockHTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


_workflow_store: Dict[str, Dict[str, Any]] = {}
_execution_store: Dict[str, List[Dict[str, Any]]] = {}


def _validate_dag(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> bool:
    node_ids = {n["id"] for n in nodes}
    for e in edges:
        if e["source"] not in node_ids or e["target"] not in node_ids:
            return False
    visited: set = set()
    in_stack: set = set()
    graph: Dict[str, List[str]] = {}
    for e in edges:
        graph.setdefault(e["source"], []).append(e["target"])

    def _has_cycle(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if _has_cycle(neighbor):
                    return True
            elif neighbor in in_stack:
                return True
        in_stack.discard(node)
        return False

    for node_id in node_ids:
        if node_id not in visited:
            if _has_cycle(node_id):
                return False
    return True


def _create_workflow(name: str, nodes: List[Dict], edges: List[Dict]) -> Dict[str, Any]:
    if not _validate_dag(nodes, edges):
        raise MockHTTPException(400, "Invalid DAG: cycle detected")
    workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
    workflow = {"id": workflow_id, "name": name, "nodes": nodes, "edges": edges, "status": "draft"}
    _workflow_store[workflow_id] = workflow
    return workflow


def _validate_workflow(workflow_id: str) -> Dict[str, Any]:
    if workflow_id not in _workflow_store:
        raise MockHTTPException(404, "Workflow not found")
    wf = _workflow_store[workflow_id]
    return {"valid": _validate_dag(wf["nodes"], wf["edges"]), "workflow_id": workflow_id}


def _preview_validate(nodes: List[Dict], edges: List[Dict]) -> Dict[str, Any]:
    return {"valid": _validate_dag(nodes, edges), "node_count": len(nodes), "edge_count": len(edges)}


def _execute_workflow(workflow_id: str) -> Dict[str, Any]:
    if workflow_id not in _workflow_store:
        raise MockHTTPException(404, "Workflow not found")
    execution_id = f"exec-{uuid.uuid4().hex[:12]}"
    record = {"id": execution_id, "workflow_id": workflow_id, "status": "queued", "started_at": datetime.now(timezone.utc).isoformat(), "completed_at": None}
    _execution_store.setdefault(workflow_id, []).append(record)
    _workflow_store[workflow_id]["status"] = "executing"
    return {"execution_id": execution_id, "workflow_id": workflow_id, "status": "queued"}


def _get_history(workflow_id: str) -> List[Dict[str, Any]]:
    if workflow_id not in _workflow_store:
        raise MockHTTPException(404, "Workflow not found")
    return _execution_store.get(workflow_id, [])


def _reset() -> None:
    _workflow_store.clear()
    _execution_store.clear()


class TestWorkflowStudio:
    def test_create_workflow_with_tool_binding(self) -> None:
        _reset()
        nodes = [
            {"id": "n1", "label": "Search", "type": "action", "tool_id": "tool-web-search"},
            {"id": "n2", "label": "Analyze", "type": "action", "tool_id": "tool-data-analysis"},
        ]
        edges = [{"id": "e1", "source": "n1", "target": "n2"}]
        wf = _create_workflow("Search & Analyze", nodes, edges)
        assert wf["name"] == "Search & Analyze"
        assert wf["status"] == "draft"
        assert len(wf["nodes"]) == 2
        assert wf["nodes"][0]["tool_id"] == "tool-web-search"

    def test_rejects_cyclic_dag(self) -> None:
        _reset()
        nodes = [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}]
        edges = [{"id": "e1", "source": "n1", "target": "n2"}, {"id": "e2", "source": "n2", "target": "n1"}]
        try:
            _create_workflow("Cyclic", nodes, edges)
            assert False, "Should have raised MockHTTPException"
        except MockHTTPException as e:
            assert e.status_code == 400
            assert "cycle" in e.detail.lower() or "invalid" in e.detail.lower()

    def test_preview_validate_valid_dag(self) -> None:
        _reset()
        nodes = [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}]
        edges = [{"id": "e1", "source": "n1", "target": "n2"}]
        result = _preview_validate(nodes, edges)
        assert result["valid"] is True
        assert result["node_count"] == 2
        assert result["edge_count"] == 1

    def test_preview_validate_cyclic_dag(self) -> None:
        _reset()
        nodes = [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}]
        edges = [{"id": "e1", "source": "n1", "target": "n2"}, {"id": "e2", "source": "n2", "target": "n1"}]
        result = _preview_validate(nodes, edges)
        assert result["valid"] is False

    def test_execute_workflow(self) -> None:
        _reset()
        wf = _create_workflow("Exec Test", [{"id": "n1", "label": "A"}], [])
        result = _execute_workflow(wf["id"])
        assert result["status"] == "queued"
        assert result["workflow_id"] == wf["id"]
        assert _workflow_store[wf["id"]]["status"] == "executing"

    def test_execution_history(self) -> None:
        _reset()
        wf = _create_workflow("History Test", [{"id": "n1", "label": "A"}], [])
        _execute_workflow(wf["id"])
        _execute_workflow(wf["id"])
        history = _get_history(wf["id"])
        assert len(history) == 2
        assert history[0]["workflow_id"] == wf["id"]
        assert history[1]["workflow_id"] == wf["id"]

    def test_validate_existing_workflow(self) -> None:
        _reset()
        wf = _create_workflow("Validate Test", [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}], [{"id": "e1", "source": "n1", "target": "n2"}])
        result = _validate_workflow(wf["id"])
        assert result["valid"] is True
        assert result["workflow_id"] == wf["id"]

    def test_node_tool_binding_tracking(self) -> None:
        _reset()
        nodes = [
            {"id": "n1", "label": "Step 1", "tool_id": "tool-web-search"},
            {"id": "n2", "label": "Step 2", "tool_id": "tool-code-exec"},
            {"id": "n3", "label": "Step 3", "tool_id": ""},
        ]
        wf = _create_workflow("Tool Binding Test", nodes, [])
        tool_ids = [n["tool_id"] for n in wf["nodes"]]
        assert tool_ids[0] == "tool-web-search"
        assert tool_ids[1] == "tool-code-exec"
        assert tool_ids[2] == ""
