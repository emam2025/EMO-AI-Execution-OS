import React from "react";

/**
 * Memory Explorer — Coming Soon | Read-Only Stub
 *
 * This screen is intentionally a stub to prevent misleading users into
 * thinking Memory OS is active. No fabricated data, no mock visualizations.
 *
 * Reference: docs/event_stream_contract.md — Future Compatibility section
 * Memory Explorer will be activated in P3 after Memory OS integration.
 */
export const MemoryExplorer: React.FC = () => {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Memory Explorer</h1>
      <div className="p-8 border-2 border-dashed border-amber-300 rounded-lg bg-amber-50 text-center">
        <p className="text-lg font-semibold text-amber-700 mb-2">
          🚧 Coming Soon — Read Only
        </p>
        <p className="text-amber-600 mb-4">
          Memory OS is not yet available in this release.
          This interface will be activated in Phase P3.
        </p>
        <p className="text-sm text-amber-500">
          Reference:{" "}
          <code className="bg-amber-100 px-1 rounded">ipc/ipc_contract.md</code> —{" "}
          Future Compatibility Requirement
        </p>
        <div className="mt-4 p-4 bg-white rounded border text-left text-sm text-gray-600">
          <p className="font-mono mb-1">$ memory status</p>
          <p className="text-gray-400">→ Memory OS: not connected</p>
          <p className="text-gray-400">→ Cognitive index: unavailable</p>
          <p className="text-gray-400">→ Skill graph: pending activation</p>
        </div>
        <a
          href="#"
          className="inline-block mt-4 text-sm text-blue-600 underline"
          onClick={(e) => { e.preventDefault(); window.open("#"); }}
        >
          Documentation: Memory OS Integration Guide →
        </a>
      </div>
    </div>
  );
};
