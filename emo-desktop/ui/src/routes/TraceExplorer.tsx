import React from "react";
import { useRuntimeStore } from "../stores/runtime";

export const TraceExplorer: React.FC = () => {
  const { traceCache, eventFilter, setEventFilter } = useRuntimeStore();
  const traces = Array.from(traceCache.values());

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Trace Explorer</h1>
      <div className="mb-4">
        <input
          type="text"
          placeholder="Filter by trace ID (og_...)"
          className="w-full p-2 border rounded"
          value={eventFilter ?? ""}
          onChange={(e) => setEventFilter(e.target.value || null)}
        />
      </div>
      {traces.length === 0 && (
        <p className="text-gray-400">
          No traces cached. Run an intent to see execution traces.
        </p>
      )}
      <div className="space-y-3">
        {traces.map((t) => (
          <div key={t.trace_id} className="border rounded-lg p-4">
            <div className="flex justify-between items-start">
              <div>
                <p className="font-mono text-sm">{t.trace_id}</p>
                <p className="text-gray-500 text-sm">
                  {t.intent} — {t.tenant_id}
                </p>
              </div>
              <span
                className={`px-2 py-1 rounded text-xs font-medium ${
                  t.valid ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                }`}
              >
                {t.valid ? "valid" : "invalid"}
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              {t.events.length} events
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};
