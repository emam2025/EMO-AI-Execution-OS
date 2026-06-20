"use client";

import { useState } from "react";
import { WorkflowNode, WorkflowEdge } from "@/lib/api/workflow";

interface DAGCanvasProps {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  onSelectNode: (node: WorkflowNode) => void;
  onConnect: (source: string, target: string) => void;
}

export default function DAGCanvas({
  nodes,
  edges,
  onSelectNode,
  onConnect,
}: DAGCanvasProps) {
  const [dragFrom, setDragFrom] = useState<string | null>(null);

  const handleNodeClick = (node: WorkflowNode) => {
    if (dragFrom && dragFrom !== node.id) {
      onConnect(dragFrom, node.id);
      setDragFrom(null);
    } else {
      onSelectNode(node);
    }
  };

  return (
    <div className="relative w-full h-full bg-gray-50 border rounded overflow-auto">
      <svg className="w-full h-full">
        {edges.map((edge) => {
          const source = nodes.find((n) => n.id === edge.source);
          const target = nodes.find((n) => n.id === edge.target);
          if (!source || !target) return null;
          return (
            <line
              key={edge.id}
              x1={source.x + 60}
              y1={source.y + 20}
              x2={target.x}
              y2={target.y + 20}
              stroke="#666"
              strokeWidth={2}
              markerEnd="url(#arrowhead)"
            />
          );
        })}
        <defs>
          <marker
            id="arrowhead"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#666" />
          </marker>
        </defs>
        {nodes.map((node) => (
          <g
            key={node.id}
            transform={`translate(${node.x}, ${node.y})`}
            onClick={() => handleNodeClick(node)}
            className="cursor-pointer"
            onMouseDown={() => setDragFrom(node.id)}
          >
            <rect
              width="120"
              height="40"
              rx="6"
              fill={
                node.type === "trigger"
                  ? "#22c55e"
                  : node.type === "condition"
                  ? "#eab308"
                  : node.type === "output"
                  ? "#ef4444"
                  : "#3b82f6"
              }
              stroke="#333"
              strokeWidth={1}
            />
            <text
              x="60"
              y="25"
              textAnchor="middle"
              fill="white"
              fontSize="12"
            >
              {node.label}
            </text>
          </g>
        ))}
      </svg>
      {nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-400">
          Click &quot;Add Node&quot; to start building your workflow
        </div>
      )}
    </div>
  );
}
