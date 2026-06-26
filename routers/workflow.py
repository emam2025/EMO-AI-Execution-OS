"""Workflow API Router.

FastAPI endpoints for workflow management, validation, execution submission, and history.
No execution logic — stores, validates, and routes workflows only.

Ref: Phase P Batch 3 + P Batch 5 (P.6 — Workflow Studio)
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from middleware.auth import require_auth

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

_workflow_store: Dict[str, Dict[str, Any]] = {}
_execution_store: Dict[str, List[Dict[str, Any]]] = {}


class NodeRequest(BaseModel):
    id: str
    label: str
    type: str = "action"
    x: int = 0
    y: int = 0
    tool_id: str = ""


class EdgeRequest(BaseModel):
    id: str
    source: str
    target: str


class WorkflowRequest(BaseModel):
    name: str
    nodes: List[NodeRequest] = []
    edges: List[EdgeRequest] = []


class WorkflowResponse(BaseModel):
    id: str
    name: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    status: str


class ValidateRequest(BaseModel):
    nodes: List[NodeRequest]
    edges: List[EdgeRequest]


class PreviewValidateRequest(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


def _validate_dag(nodes: List[Any], edges: List[Any]) -> bool:
    """Validate that the workflow graph is a DAG (no cycles, all deps exist)."""
    node_ids = set()
    for n in nodes:
        if hasattr(n, "id"):
            node_ids.add(n.id)
        elif isinstance(n, dict):
            node_ids.add(n["id"])

    for e in edges:
        src = e.source if hasattr(e, "source") else e["source"]
        tgt = e.target if hasattr(e, "target") else e["target"]
        if src not in node_ids or tgt not in node_ids:
            return False

    visited: set = set()
    in_stack: set = set()
    graph: Dict[str, List[str]] = {}
    for e in edges:
        src = e.source if hasattr(e, "source") else e["source"]
        tgt = e.target if hasattr(e, "target") else e["target"]
        graph.setdefault(src, []).append(tgt)

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


@router.get("", response_model=List[WorkflowResponse])
def list_workflows(user: dict = Depends(require_auth())) -> List[Dict[str, Any]]:
    """Return all stored workflows."""
    return list(_workflow_store.values())


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str, user: dict = Depends(require_auth())) -> Dict[str, Any]:
    """Return a specific workflow by ID."""
    if workflow_id not in _workflow_store:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _workflow_store[workflow_id]


@router.post("", response_model=WorkflowResponse, status_code=201)
def create_workflow(request: WorkflowRequest, user: dict = Depends(require_auth())) -> Dict[str, Any]:
    """Create a new workflow. Validates DAG before saving."""
    if not _validate_dag(request.nodes, request.edges):
        raise HTTPException(status_code=400, detail="Invalid DAG: cycle detected or missing edge references")

    workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
    workflow = {
        "id": workflow_id,
        "name": request.name,
        "nodes": [n.model_dump() for n in request.nodes],
        "edges": [e.model_dump() for e in request.edges],
        "status": "draft",
    }
    _workflow_store[workflow_id] = workflow
    return workflow


@router.post("/preview-validate", response_model=Dict[str, Any])
def preview_validate(request: PreviewValidateRequest, user: dict = Depends(require_auth())) -> Dict[str, Any]:
    """Validate a DAG without storing it (for UI preview)."""
    is_valid = _validate_dag(request.nodes, request.edges)
    return {"valid": is_valid, "node_count": len(request.nodes), "edge_count": len(request.edges)}


@router.post("/{workflow_id}/validate", response_model=Dict[str, Any])
def validate_workflow(workflow_id: str, user: dict = Depends(require_auth())) -> Dict[str, Any]:
    """Validate an existing workflow's DAG."""
    if workflow_id not in _workflow_store:
        raise HTTPException(status_code=404, detail="Workflow not found")
    workflow = _workflow_store[workflow_id]
    is_valid = _validate_dag(workflow["nodes"], workflow["edges"])
    return {"valid": is_valid, "workflow_id": workflow_id}


@router.post("/{workflow_id}/submit", response_model=WorkflowResponse)
def submit_workflow(workflow_id: str, user: dict = Depends(require_auth())) -> Dict[str, Any]:
    """Submit a workflow for execution (status change only, no execution)."""
    if workflow_id not in _workflow_store:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = _workflow_store[workflow_id]
    if workflow["status"] != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot submit workflow in status '{workflow['status']}'")

    workflow["status"] = "submitted"
    return workflow


@router.post("/{workflow_id}/execute", response_model=Dict[str, Any])
def execute_workflow(workflow_id: str, user: dict = Depends(require_auth())) -> Dict[str, Any]:
    """Submit a workflow for execution via UnifiedRuntimeAPI (status change only)."""
    if workflow_id not in _workflow_store:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = _workflow_store[workflow_id]
    execution_id = f"exec-{uuid.uuid4().hex[:12]}"
    record = {
        "id": execution_id,
        "workflow_id": workflow_id,
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    _execution_store.setdefault(workflow_id, []).append(record)
    workflow["status"] = "executing"
    return {"execution_id": execution_id, "workflow_id": workflow_id, "status": "queued"}


@router.get("/{workflow_id}/history", response_model=List[Dict[str, Any]])
def get_execution_history(workflow_id: str, user: dict = Depends(require_auth())) -> List[Dict[str, Any]]:
    """Return execution history for a workflow."""
    if workflow_id not in _workflow_store:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _execution_store.get(workflow_id, [])
