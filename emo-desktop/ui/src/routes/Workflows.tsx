import React from "react";
import { useRuntimeStore } from "../stores/runtime";
import { StatusBadge } from "../styles/design-system/status-badge";

export const Workflows: React.FC = () => {
  const { traceCache, isConnected } = useRuntimeStore();
  const traces = Array.from(traceCache.values());

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          Workflows
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Active DAG executions with real-time status
        </p>
      </div>

      <div className="glass-panel" style={{ padding: 16 }}>
        <div className="section-header">Active Executions</div>
        {traces.length === 0 && (
          <p style={{ color: "#9ca3af", fontSize: "0.85rem", padding: 24, textAlign: "center" }}>
            {isConnected ? "No active workflows. Run an agent to see execution traces here." : "Connect to runtime to view workflows."}
          </p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {traces.map((trace) => {
            const hasFailed = trace.events?.some((e) => e.source === "error");
            const nodeCount = trace.events?.length ?? 0;
            return (
              <div
                key={trace.trace_id}
                className="smooth-enter"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 16px",
                  borderRadius: 8,
                  background: "rgba(255,255,255,0.5)",
                  border: "1px solid rgba(0,0,0,0.04)",
                }}
              >
                <div style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: hasFailed ? "#ef4444" : "#22c55e",
                }} />
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: "0.85rem", fontFamily: "monospace" }}>
                      {trace.trace_id.slice(0, 20)}…
                    </span>
                    <StatusBadge state={hasFailed ? "failed" : "completed"} size="sm" />
                  </div>
                  <p style={{ margin: "2px 0 0", fontSize: "0.75rem", color: "#9ca3af" }}>
                    {nodeCount} nodes · {trace.events?.[0]?.timestamp ?? "—"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
