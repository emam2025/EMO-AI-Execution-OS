"use client";

import { useState } from "react";
import DAGCanvas from "@/components/workflow/DAGCanvas";
import NodeEditor from "@/components/workflow/NodeEditor";
import ToolBinder from "@/components/workflow/ToolBinder";
import { WorkflowNode, WorkflowEdge } from "@/lib/api/workflow";

interface ToolBinding {
  nodeId: string;
  toolId: string;
  toolName: string;
}

interface ExecutionRecord {
  id: string;
  workflowId: string;
  status: string;
  startedAt: string;
  completedAt: string | null;
}

export default function WorkflowPage() {
  const [nodes, setNodes] = useState<WorkflowNode[]>([]);
  const [edges, setEdges] = useState<WorkflowEdge[]>([]);
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null);
  const [toolBindings, setToolBindings] = useState<ToolBinding[]>([]);
  const [history, setHistory] = useState<ExecutionRecord[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);

  const handleAddNode = (label: string) => {
    const newNode: WorkflowNode = {
      id: `node-${Date.now()}`,
      label,
      type: "action",
      x: 100 + nodes.length * 50,
      y: 100,
    };
    setNodes((prev) => [...prev, newNode]);
  };

  const handleUpdateNode = (updated: WorkflowNode) => {
    setNodes((prev) =>
      prev.map((n) => (n.id === updated.id ? updated : n))
    );
    setSelectedNode(null);
  };

  const handleDeleteNode = (id: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== id));
    setEdges((prev) =>
      prev.filter((e) => e.source !== id && e.target !== id)
    );
    setToolBindings((prev) => prev.filter((b) => b.nodeId !== id));
    setSelectedNode(null);
  };

  const handleConnect = (source: string, target: string) => {
    const newEdge: WorkflowEdge = {
      id: `edge-${source}-${target}`,
      source,
      target,
    };
    setEdges((prev) => [...prev, newEdge]);
  };

  const handleBindTool = (nodeId: string, toolId: string, toolName: string) => {
    setToolBindings((prev) => {
      const filtered = prev.filter((b) => b.nodeId !== nodeId);
      return [...filtered, { nodeId, toolId, toolName }];
    });
  };

  const handleExport = () => {
    const dag = { nodes, edges, toolBindings };
    const blob = new Blob([JSON.stringify(dag, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "workflow.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = (json: string) => {
    try {
      const dag = JSON.parse(json);
      if (dag.nodes && dag.edges) {
        setNodes(dag.nodes);
        setEdges(dag.edges);
        if (dag.toolBindings) setToolBindings(dag.toolBindings);
      }
    } catch {
      console.error("Invalid workflow JSON");
    }
  };

  const handlePreview = () => {
    setPreviewMode((prev) => !prev);
  };

  const handleValidate = async () => {
    const res = await fetch("/api/workflows/preview-validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nodes, edges }),
    });
    return res.json();
  };

  return (
    <div className="flex h-screen">
      <div className="w-1/4 border-r p-4">
        <h1 className="text-xl font-bold mb-4">Workflow Studio</h1>
        <button
          onClick={() => handleAddNode("New Action")}
          className="bg-blue-500 text-white px-4 py-2 rounded mb-2"
        >
          Add Node
        </button>
        <button
          onClick={handleExport}
          className="bg-green-500 text-white px-4 py-2 rounded mb-2 ml-2"
        >
          Export JSON
        </button>
        <button
          onClick={handlePreview}
          className="bg-yellow-500 text-white px-4 py-2 rounded mb-2 ml-2"
        >
          {previewMode ? "Edit Mode" : "Preview"}
        </button>
        <button
          onClick={() => setShowHistory((prev) => !prev)}
          className="bg-gray-500 text-white px-4 py-2 rounded mb-2 ml-2"
        >
          History
        </button>

        {selectedNode && (
          <div className="mt-4">
            <NodeEditor
              node={selectedNode}
              onUpdate={handleUpdateNode}
              onDelete={handleDeleteNode}
            />
            <ToolBinder
              nodeId={selectedNode.id}
              currentBinding={toolBindings.find((b) => b.nodeId === selectedNode.id)}
              onBindTool={handleBindTool}
            />
          </div>
        )}

        {showHistory && (
          <div className="mt-4 border-t pt-4">
            <h2 className="font-bold mb-2">Execution History</h2>
            {history.length === 0 ? (
              <p className="text-gray-500">No executions yet</p>
            ) : (
              <ul>
                {history.map((h) => (
                  <li key={h.id} className="text-sm py-1">
                    {h.status} — {h.startedAt}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
      <div className="w-3/4">
        <DAGCanvas
          nodes={nodes}
          edges={edges}
          onSelectNode={setSelectedNode}
          onConnect={handleConnect}
        />
      </div>
    </div>
  );
}
