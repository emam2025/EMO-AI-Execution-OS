import React, { useState } from "react";
import { useRuntimeStore } from "../stores/runtime";
import { TimelineNode, ExecutionTimeline, type NodeState } from "../styles/design-system/timeline-node";

export const TraceExplorer: React.FC = () => {
  const { traceCache, eventFilter, setEventFilter } = useRuntimeStore();
  const traces = Array.from(traceCache.values());
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);

  const activeTrace = traces.find((t) => t.trace_id === selectedTrace);

  // Convert trace events to timeline nodes
  const timelineNodes = activeTrace?.events.map((e, i) => {
    const stateMap: Record<string, NodeState> = {
      plan_proposed: "completed",
      plan_executed: "completed",
      node_completed: "completed",
      node_failed: "failed",
      agent_warning: "failed",
      task_started: "completed",
      runtime_error: "failed",
      trace_indexed: "completed",
    };
    const state: NodeState = stateMap[e.event] ?? "completed";
    return {
      key: i,
      label: e.event,
      state,
      description: e.data ? `${Object.keys(e.data).join(", ")}` : undefined,
      durationMs: e.data?.duration_ms as number | undefined,
      isLast: i === activeTrace.events.length - 1,
    };
  });

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
            Trace Explorer
          </h1>
          <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
            Execution traces with interactive timeline
          </p>
        </div>
        <input
          type="text"
          placeholder="Filter by trace ID…"
          value={eventFilter ?? ""}
          onChange={(e) => setEventFilter(e.target.value || null)}
          className="glass-input"
          style={{ marginLeft: "auto", width: 220 }}
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 16, flex: 1, minHeight: 0 }}>
        {/* Trace list */}
        <div className="glass-panel" style={{ padding: 12, overflow: "auto" }}>
          <div className="section-header">All Traces ({traces.length})</div>
          {traces.length === 0 && (
            <p style={{ color: "#9ca3af", fontSize: "0.8rem", textAlign: "center", padding: 24 }}>
              No traces yet. Run an intent to generate execution traces.
            </p>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {traces.map((t) => (
              <button
                key={t.trace_id}
                onClick={() => setSelectedTrace(t.trace_id)}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 2,
                  padding: "8px 10px",
                  borderRadius: 6,
                  border: "none",
                  background: selectedTrace === t.trace_id
                    ? "rgba(59,130,246,0.1)"
                    : "transparent",
                  cursor: "pointer",
                  transition: "all 0.1s ease-out",
                  textAlign: "left",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    className={`status-badge ${t.valid ? "status-badge-active" : "status-badge-down"}`}
                    style={{ fontSize: "0.6rem", padding: "1px 6px" }}
                  >
                    {t.valid ? "valid" : "invalid"}
                  </span>
                  <span style={{ fontFamily: "monospace", fontSize: "0.75rem", color: "#374151" }}>
                    {t.trace_id.slice(0, 16)}…
                  </span>
                </div>
                <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                  {t.intent} · {t.events.length} events
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Timeline */}
        <div className="glass-panel" style={{ padding: 16, overflow: "auto" }}>
          {activeTrace ? (
            <>
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <h2 style={{ fontSize: "0.95rem", fontWeight: 600, margin: 0, fontFamily: "monospace" }}>
                    {activeTrace.trace_id}
                  </h2>
                  <span
                    className={`status-badge ${activeTrace.valid ? "status-badge-active" : "status-badge-down"}`}
                  >
                    {activeTrace.valid ? "Valid" : "Invalid"}
                  </span>
                </div>
                <p style={{ fontSize: "0.8rem", color: "#6b7280", margin: "2px 0 0" }}>
                  Intent: {activeTrace.intent} · Tenant: {activeTrace.tenant_id} · {activeTrace.events.length} events
                </p>
              </div>
              <ExecutionTimeline>
                {timelineNodes?.map((node) => (
                  <TimelineNode key={node.key} {...node} />
                ))}
              </ExecutionTimeline>
            </>
          ) : (
            <div style={{ textAlign: "center", padding: 48 }}>
              <p style={{ color: "#9ca3af", fontSize: "0.85rem", marginBottom: 8 }}>◈</p>
              <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>
                Select a trace from the list to view its execution timeline.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
