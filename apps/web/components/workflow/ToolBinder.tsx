"use client";

import { useState } from "react";

interface ToolOption {
  id: string;
  name: string;
  provider: string;
}

interface ToolBinding {
  nodeId: string;
  toolId: string;
  toolName: string;
}

interface ToolBinderProps {
  nodeId: string;
  currentBinding: ToolBinding | undefined;
  onBindTool: (nodeId: string, toolId: string, toolName: string) => void;
}

const AVAILABLE_TOOLS: ToolOption[] = [
  { id: "tool-web-search", name: "Web Search", provider: "openai" },
  { id: "tool-code-exec", name: "Code Execution", provider: "openai" },
  { id: "tool-data-analysis", name: "Data Analysis", provider: "anthropic" },
  { id: "tool-image-gen", name: "Image Generation", provider: "openai" },
  { id: "tool-text-summary", name: "Text Summarization", provider: "anthropic" },
];

export default function ToolBinder({ nodeId, currentBinding, onBindTool }: ToolBinderProps) {
  const [selectedToolId, setSelectedToolId] = useState<string>(currentBinding?.toolId || "");

  const handleBind = () => {
    const tool = AVAILABLE_TOOLS.find((t) => t.id === selectedToolId);
    if (tool) {
      onBindTool(nodeId, tool.id, tool.name);
    }
  };

  return (
    <div className="mt-4 border-t pt-4">
      <h3 className="font-bold text-sm mb-2">Bind Tool</h3>
      <select
        value={selectedToolId}
        onChange={(e) => setSelectedToolId(e.target.value)}
        className="w-full border rounded px-2 py-1 text-sm mb-2"
      >
        <option value="">Select a tool...</option>
        {AVAILABLE_TOOLS.map((tool) => (
          <option key={tool.id} value={tool.id}>
            {tool.name} ({tool.provider})
          </option>
        ))}
      </select>
      <button
        onClick={handleBind}
        disabled={!selectedToolId}
        className="bg-purple-500 text-white px-3 py-1 rounded text-sm disabled:opacity-50"
      >
        Bind Tool
      </button>
      {currentBinding && (
        <p className="text-xs text-gray-500 mt-1">
          Current: {currentBinding.toolName}
        </p>
      )}
    </div>
  );
}
