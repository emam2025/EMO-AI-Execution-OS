"""Workflow API Client — TypeScript types and API helpers.

Pure types and fetch wrappers for the Workflow Studio frontend.
No runtime imports, no agent imports, no sandbox imports.

Ref: Phase P Batch 2
"""

export interface WorkflowNode {
  id: string;
  label: string;
  type: "action" | "condition" | "trigger" | "output";
  x: number;
  y: number;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
}

export interface Workflow {
  id: string;
  name: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  status: "draft" | "validated" | "submitted";
  createdAt: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function fetchWorkflows(): Promise<Workflow[]> {
  const res = await fetch(`${API_BASE}/api/workflows`);
  if (!res.ok) throw new Error("Failed to fetch workflows");
  return res.json();
}

export async function fetchWorkflow(id: string): Promise<Workflow> {
  const res = await fetch(`${API_BASE}/api/workflows/${id}`);
  if (!res.ok) throw new Error("Failed to fetch workflow");
  return res.json();
}

export async function saveWorkflow(workflow: Omit<Workflow, "id" | "createdAt">): Promise<Workflow> {
  const res = await fetch(`${API_BASE}/api/workflows`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflow),
  });
  if (!res.ok) throw new Error("Failed to save workflow");
  return res.json();
}

export async function submitWorkflow(id: string): Promise<{ submissionId: string }> {
  const res = await fetch(`${API_BASE}/api/workflows/${id}/submit`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to submit workflow");
  return res.json();
}
