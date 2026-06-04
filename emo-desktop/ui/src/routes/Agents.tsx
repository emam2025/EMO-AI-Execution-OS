import React from "react";
import { useRuntimeStore } from "../stores/runtime";
import { StatusBadge } from "../styles/design-system/status-badge";
import { EmptyState } from "../styles/design-system/empty-state";
import { LoadingSkeleton } from "../styles/design-system/loading-skeleton";

export const Agents: React.FC = () => {
  const { health, isConnected, telemetry } = useRuntimeStore();

  if (!isConnected) {
    return <EmptyState icon="🔌" title="Runtime Disconnected" description="Connect to the runtime to view agent status." />;
  }

  if (!health && !telemetry) {
    return <LoadingSkeleton variant="list" lines={3} />;
  }

  const agentCount = telemetry?.active_agents ?? 0;

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          Agents
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Agent health, capabilities, and runtime status
        </p>
      </div>

      <div className="glass-panel" style={{ padding: 16 }}>
        <div className="section-header">Runtime Agents</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {agentCount === 0 ? (
            <p style={{ padding: 24, textAlign: "center", color: "#9ca3af", fontSize: "0.85rem" }}>
              No agents currently running. Create a project and run an agent to get started.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="smooth-enter" style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "14px 16px", borderRadius: 8,
                background: "rgba(255,255,255,0.5)", border: "1px solid rgba(0,0,0,0.04)",
              }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontWeight: 700, fontSize: "0.9rem",
                  background: "rgba(34,197,94,0.12)", color: "#16a34a",
                }}>
                  {agentCount}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Active Agents</span>
                    <StatusBadge state="active" label="Online" size="sm" />
                  </div>
                  <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
                    {agentCount} agent{agentCount !== 1 ? "s" : ""} currently running
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="glass-panel" style={{ padding: 16, display: "flex", alignItems: "center", gap: 16 }}>
        <div>
          <div className="section-header" style={{ marginBottom: 4 }}>Connection</div>
          <StatusBadge state={isConnected ? "active" : "down"} label={isConnected ? "Connected" : "Disconnected"} />
        </div>
        <div>
          <div className="section-header" style={{ marginBottom: 4 }}>Health</div>
          <StatusBadge
            state={health?.status === "operational" ? "active" : "degraded"}
            label={health?.status ?? "Unknown"}
          />
        </div>
        <div>
          <div className="section-header" style={{ marginBottom: 4 }}>Active Tasks</div>
          <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>{telemetry?.active_agents ?? 0}</span>
        </div>
      </div>
    </div>
  );
};
