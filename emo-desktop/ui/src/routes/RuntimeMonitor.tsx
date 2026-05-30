import React from "react";
import { useRuntimeStore } from "../stores/runtime";
import { ActivityStream } from "../components/live-activity-stream/ActivityStream";

export const RuntimeMonitor: React.FC = () => {
  const { telemetry, health, gatewayMetrics, isConnected } = useRuntimeStore();

  const gaugePercent = (val: number | undefined, max: number): string => {
    if (val === undefined) return "0%";
    return `${Math.min((val / max) * 100, 100).toFixed(0)}%`;
  };

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
            Runtime Monitor
          </h1>
          <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
            Real-time system metrics · Updates every 500ms
          </p>
        </div>
        <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "#9ca3af" }}>
          Uptime: {health?.uptime_seconds ? `${Math.floor(health.uptime_seconds / 60)}m` : "--"}
        </span>
      </div>

      {/* Main metric gauges */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        {/* CPU */}
        <div className="glass-panel" style={{ padding: 20, textAlign: "center" }}>
          <div
            className="metric-card-value"
            style={{
              fontSize: "2.5rem",
              color: (telemetry?.cpu_usage ?? 0) > 80 ? "#ef4444" : "#111",
            }}
          >
            {telemetry?.cpu_usage ?? "--"}%
          </div>
          <div className="metric-card-label">CPU Usage</div>
          <div
            style={{
              marginTop: 12,
              height: 4,
              borderRadius: 2,
              background: "rgba(0,0,0,0.06)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: gaugePercent(telemetry?.cpu_usage, 100),
                height: "100%",
                borderRadius: 2,
                background: (telemetry?.cpu_usage ?? 0) > 80
                  ? "linear-gradient(90deg, #f59e0b, #ef4444)"
                  : "linear-gradient(90deg, #3b82f6, #22c55e)",
                transition: "width 0.3s ease-out",
              }}
            />
          </div>
        </div>

        {/* Memory */}
        <div className="glass-panel" style={{ padding: 20, textAlign: "center" }}>
          <div className="metric-card-value" style={{ fontSize: "2.5rem" }}>
            {telemetry?.memory_usage ?? "--"}
          </div>
          <div className="metric-card-label">Memory (MB)</div>
          <div
            style={{
              marginTop: 12,
              height: 4,
              borderRadius: 2,
              background: "rgba(0,0,0,0.06)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: gaugePercent(telemetry?.memory_usage, 16384),
                height: "100%",
                borderRadius: 2,
                background: "linear-gradient(90deg, #8b5cf6, #3b82f6)",
                transition: "width 0.3s ease-out",
              }}
            />
          </div>
        </div>

        {/* Event Latency */}
        <div className="glass-panel" style={{ padding: 20, textAlign: "center" }}>
          <div className="metric-card-value" style={{ fontSize: "2.5rem" }}>
            {telemetry?.event_latency_ms ?? "--"}
          </div>
          <div className="metric-card-label">Event Latency (ms)</div>
          <div
            style={{
              marginTop: 12,
              height: 4,
              borderRadius: 2,
              background: "rgba(0,0,0,0.06)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: gaugePercent(telemetry?.event_latency_ms, 200),
                height: "100%",
                borderRadius: 2,
                background: "linear-gradient(90deg, #22c55e, #f59e0b)",
                transition: "width 0.3s ease-out",
              }}
            />
          </div>
        </div>
      </div>

      {/* Secondary metrics grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <div className="metric-card">
          <div className="metric-card-value" style={{ fontSize: "1.1rem" }}>
            {health?.planner ? "✓" : "✗"}
          </div>
          <div className="metric-card-label">Planner</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-value" style={{ fontSize: "1.1rem" }}>
            {health?.critic ? "✓" : "✗"}
          </div>
          <div className="metric-card-label">Critic</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-value" style={{ fontSize: "1.1rem" }}>
            {health?.optimizer ? "✓" : "✗"}
          </div>
          <div className="metric-card-label">Optimizer</div>
        </div>
        <div className="metric-card">
          <div className="metric-card-value" style={{ fontSize: "1.1rem" }}>
            {health?.state_machine ? "✓" : "✗"}
          </div>
          <div className="metric-card-label">State Machine</div>
        </div>
      </div>

      {/* Gateway metrics row */}
      {gatewayMetrics && (
        <div className="glass-panel" style={{ padding: 16 }}>
          <div className="section-header">Gateway Telemetry</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            <div>
              <div className="metric-card-value" style={{ fontSize: "1rem" }}>
                ${gatewayMetrics.cost_per_token.toFixed(6)}
              </div>
              <div className="metric-card-label">Cost / Token</div>
            </div>
            <div>
              <div className="metric-card-value" style={{ fontSize: "1rem" }}>
                ${gatewayMetrics.total_session_cost.toFixed(4)}
              </div>
              <div className="metric-card-label">Session Cost</div>
            </div>
            <div>
              <div className="metric-card-value" style={{ fontSize: "1rem" }}>
                {gatewayMetrics.avg_latency_ms}ms
              </div>
              <div className="metric-card-label">Avg Latency</div>
            </div>
            <div>
              <div className="metric-card-value" style={{ fontSize: "1rem" }}>
                {gatewayMetrics.failover_count}
              </div>
              <div className="metric-card-label">Failovers</div>
            </div>
          </div>
        </div>
      )}

      {/* Activity Stream */}
      <div style={{ flex: 1, minHeight: 200 }}>
        <ActivityStream />
      </div>
    </div>
  );
};
