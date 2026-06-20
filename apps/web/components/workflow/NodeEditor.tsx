"use client";

import { useState } from "react";
import { WorkflowNode } from "@/lib/api/workflow";

interface NodeEditorProps {
  node: WorkflowNode;
  onUpdate: (node: WorkflowNode) => void;
  onDelete: (id: string) => void;
}

export default function NodeEditor({ node, onUpdate, onDelete }: NodeEditorProps) {
  const [label, setLabel] = useState(node.label);
  const [type, setType] = useState(node.type);

  const handleSave = () => {
    onUpdate({ ...node, label, type });
  };

  return (
    <div className="border rounded p-4 mt-4">
      <h2 className="text-lg font-semibold mb-2">Edit Node</h2>
      <div className="mb-2">
        <label className="block text-sm mb-1">Label</label>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          className="w-full border rounded px-2 py-1"
        />
      </div>
      <div className="mb-2">
        <label className="block text-sm mb-1">Type</label>
        <select
          value={type}
          onChange={(e) => setType(e.target.value as WorkflowNode["type"])}
          className="w-full border rounded px-2 py-1"
        >
          <option value="action">Action</option>
          <option value="condition">Condition</option>
          <option value="trigger">Trigger</option>
          <option value="output">Output</option>
        </select>
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          className="bg-blue-500 text-white px-3 py-1 rounded text-sm"
        >
          Save
        </button>
        <button
          onClick={() => onDelete(node.id)}
          className="bg-red-500 text-white px-3 py-1 rounded text-sm"
        >
          Delete
        </button>
      </div>
    </div>
  );
}
