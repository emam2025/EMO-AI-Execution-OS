import React from "react";
import { useRuntimeStore } from "../stores/runtime";
import { StatusBadge } from "../styles/design-system/status-badge";

export const Knowledge: React.FC = () => {
  const { knowledgeTree, traceCache, isConnected } = useRuntimeStore();
  const traces = Array.from(traceCache.values());

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          Knowledge
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Memory tree, knowledge graph, and execution traces
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, flex: 1 }}>
        <div className="glass-panel" style={{ padding: 16, display: "flex", flexDirection: "column" }}>
          <div className="section-header">Memory Tree</div>
          {knowledgeTree.length === 0 && (
            <p style={{ color: "#9ca3af", fontSize: "0.85rem", padding: 24, textAlign: "center" }}>
              {isConnected ? "No memory entries yet. Knowledge is built as agents execute tasks." : "Connect to see memory tree."}
            </p>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 4, overflow: "auto" }}>
            {knowledgeTree.map((node) => (
              <div key={node.id} className="smooth-enter" style={{
                padding: "10px 12px", borderRadius: 6,
                background: "rgba(255,255,255,0.4)", border: "1px solid rgba(0,0,0,0.04)",
                marginLeft: node.type === "entity" ? 16 : node.type === "concept" ? 32 : 0,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: "0.8rem" }}>
                    {node.type === "memory" ? "📄" : node.type === "entity" ? "🔷" : "🔗"}
                  </span>
                  <span style={{ fontSize: "0.85rem", fontWeight: 500 }}>{node.label}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-panel" style={{ padding: 16, display: "flex", flexDirection: "column" }}>
          <div className="section-header">Recent Traces</div>
          {traces.length === 0 && (
            <p style={{ color: "#9ca3af", fontSize: "0.85rem", padding: 24, textAlign: "center" }}>
              No execution traces recorded yet.
            </p>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, overflow: "auto" }}>
            {traces.slice(0, 10).map((trace) => {
              const hasFailed = trace.events?.some((e) => e.source === "error");
              return (
                <div key={trace.trace_id} className="smooth-enter" style={{
                  padding: "10px 12px", borderRadius: 6,
                  background: "rgba(255,255,255,0.4)", border: "1px solid rgba(0,0,0,0.04)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <StatusBadge state={hasFailed ? "failed" : "completed"} size="sm" />
                    <span style={{ fontSize: "0.8rem", fontWeight: 500, fontFamily: "monospace" }}>
                      {trace.trace_id.slice(0, 16)}…
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
