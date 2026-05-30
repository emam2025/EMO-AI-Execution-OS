import React from "react";
import { useRuntimeStore } from "../stores/runtime";
import { ActivityStream } from "../components/live-activity-stream/ActivityStream";

type Route = "dashboard" | "runtime-monitor" | "trace-explorer" | "model-gateway" | "agent-studio" | "project-center" | "settings" | "memory-explorer";

interface DashboardProps {
  onNavigate: (route: Route) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate }) => {
  const { health, telemetry, gatewayMetrics, isConnected } = useRuntimeStore();

  const quickActions: { label: string; route: Route; desc: string }[] = [
    { label: "Monitor Runtime", route: "runtime-monitor", desc: "CPU, memory, queue" },
    { label: "Explore Traces", route: "trace-explorer", desc: "Execution timeline" },
    { label: "Model Gateway", route: "model-gateway", desc: "Routing, cost, failover" },
    { label: "Settings", route: "settings", desc: "Providers, auth, about" },
  ];

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
            Dashboard
          </h1>
          <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
            {isConnected ? "Runtime connected and operational" : "Runtime disconnected"}
          </p>
        </div>
        <span
          className={`status-badge ${isConnected ? "status-badge-active" : "status-badge-down"}`}
          style={{ marginLeft: "auto" }}
        >
          <span className={isConnected ? "live-dot" : "live-dot-disconnected"} />
          {isConnected ? "Live" : "Offline"}
        </span>
      </div>

      {/* Metric cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <div className="metric-card">
          <div className="metric-card-value">{telemetry?.cpu_usage ?? "--"}%</div>
          <div className="metric-card-label">CPU Usage</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-value">{telemetry?.memory_usage ?? "--"}</div>
          <div className="metric-card-label">Memory (MB)</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-value">{telemetry?.active_agents ?? "--"}</div>
          <div className="metric-card-label">Active Agents</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-value">{telemetry?.queued_tasks ?? "--"}</div>
          <div className="metric-card-label">Queued Tasks</div>
        </div>
      </div>

      {/* Quick Actions + Gateway summary */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, flex: 1, minHeight: 0 }}>
        {/* Quick Actions */}
        <div className="glass-panel" style={{ padding: 16, display: "flex", flexDirection: "column" }}>
          <div className="section-header">Quick Actions</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {quickActions.map((action) => (
              <button
                key={action.route}
                onClick={() => onNavigate(action.route)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "10px 14px",
                  borderRadius: 8,
                  border: "1px solid rgba(0,0,0,0.06)",
                  background: "rgba(255,255,255,0.5)",
                  cursor: "pointer",
                  transition: "all 0.12s ease-out",
                  textAlign: "left",
                }}
              >
                <div style={{ flex: 1 }}>
                  <p style={{ fontWeight: 600, fontSize: "0.85rem", margin: 0 }}>{action.label}</p>
                  <p style={{ margin: 0, color: "#6b7280", fontSize: "0.75rem" }}>{action.desc}</p>
                </div>
                <span style={{ color: "#9ca3af", fontSize: "0.85rem" }}>→</span>
              </button>
            ))}
          </div>
        </div>

        {/* Gateway Summary */}
        <div className="glass-panel" style={{ padding: 16, display: "flex", flexDirection: "column" }}>
          <div className="section-header">Model Gateway</div>
          {gatewayMetrics ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div className="metric-card" style={{ padding: 12 }}>
                  <div className="metric-card-value" style={{ fontSize: "1.2rem" }}>
                    ${gatewayMetrics.total_session_cost.toFixed(4)}
                  </div>
                  <div className="metric-card-label">Session Cost</div>
                </div>
                <div className="metric-card" style={{ padding: 12 }}>
                  <div className="metric-card-value" style={{ fontSize: "1.2rem" }}>
                    {gatewayMetrics.avg_latency_ms}ms
                  </div>
                  <div className="metric-card-label">Avg Latency</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, fontSize: "0.8rem", color: "#6b7280" }}>
                <span>Failovers: {gatewayMetrics.failover_count}</span>
                <span>·</span>
                <span>Success: {gatewayMetrics.provider_success_rate}%</span>
                <span>·</span>
                <span>Requests: {gatewayMetrics.total_requests}</span>
              </div>
            </div>
          ) : (
            <p style={{ color: "#9ca3af", fontSize: "0.85rem", margin: "auto" }}>
              No gateway data yet.
            </p>
          )}
          <button
            onClick={() => onNavigate("model-gateway")}
            style={{
              marginTop: "auto",
              padding: "8px",
              borderRadius: 6,
              border: "1px solid rgba(0,0,0,0.06)",
              background: "transparent",
              fontSize: "0.8rem",
              color: "#2563eb",
              cursor: "pointer",
            }}
          >
            View Full Gateway Stats →
          </button>
        </div>
      </div>

      {/* Activity Stream */}
      <div style={{ flex: 1, minHeight: 200 }}>
        <ActivityStream />
      </div>
    </div>
  );
};
