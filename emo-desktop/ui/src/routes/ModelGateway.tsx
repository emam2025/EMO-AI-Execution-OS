import React from "react";
import { useRuntimeStore } from "../stores/runtime";

export const ModelGateway: React.FC = () => {
  const { gatewayMetrics, routingStatus } = useRuntimeStore();

  const providers = routingStatus?.routing_table ?? [];
  const activeRoutes = routingStatus?.active_routes ?? [];

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          Model Gateway
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Live routing, failover status, and cost tracking
        </p>
      </div>

      {/* Routing status header */}
      <div className="glass-panel" style={{ padding: 16, display: "flex", alignItems: "center", gap: 20 }}>
        <div>
          <div className="section-header" style={{ marginBottom: 4 }}>Failover Readiness</div>
          <span
            className={`status-badge ${routingStatus?.failover_ready ? "status-badge-active" : "status-badge-down"}`}
          >
            {routingStatus?.failover_ready ? "Ready" : "Not Ready"}
          </span>
        </div>
        <div>
          <div className="section-header" style={{ marginBottom: 4 }}>Active Routes</div>
          <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>
            {activeRoutes.length > 0 ? activeRoutes.join(", ") : "None"}
          </span>
        </div>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div className="section-header" style={{ marginBottom: 4 }}>Cost Tracking</div>
          <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>
            ${routingStatus?.cost_tracking.total_spent_usd.toFixed(2) ?? "0.00"} / $
            {routingStatus?.cost_tracking.budget_limit_usd.toFixed(2) ?? "100.00"}
          </span>
        </div>
      </div>

      {/* Provider routing table */}
      <div className="glass-panel" style={{ padding: 16, flex: 1 }}>
        <div className="section-header">Routing Table</div>
        {providers.length === 0 && (
          <p style={{ color: "#9ca3af", fontSize: "0.85rem", padding: 24, textAlign: "center" }}>
            No providers configured. Go to Settings → Providers to add API keys.
          </p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {providers.map((entry, i) => (
            <div
              key={entry.provider}
              className="smooth-enter"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "12px 14px",
                borderRadius: 8,
                background: "rgba(255,255,255,0.5)",
                border: "1px solid rgba(0,0,0,0.04)",
                animationDelay: `${i * 30}ms`,
              }}
            >
              {/* Priority indicator */}
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 8,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 700,
                  fontSize: "0.8rem",
                  background:
                    entry.status === "active"
                      ? "rgba(34,197,94,0.12)"
                      : entry.status === "rate_limited"
                        ? "rgba(249,115,22,0.12)"
                        : "rgba(239,68,68,0.12)",
                  color:
                    entry.status === "active"
                      ? "#16a34a"
                      : entry.status === "rate_limited"
                        ? "#ea580c"
                        : "#dc2626",
                }}
              >
                {entry.priority}
              </div>

              <div style={{ flex: 1 }}>
                <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{entry.provider}</span>
              </div>

              <span
                className={`status-badge status-badge-${entry.status}`}
              >
                {entry.status === "rate_limited" ? "rate limited" : entry.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Gateway metrics */}
      {gatewayMetrics && (
        <div className="glass-panel" style={{ padding: 16 }}>
          <div className="section-header">Aggregated Metrics</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            <div className="metric-card">
              <div className="metric-card-value" style={{ fontSize: "1rem" }}>
                {gatewayMetrics.total_requests}
              </div>
              <div className="metric-card-label">Total Requests</div>
            </div>
            <div className="metric-card">
              <div className="metric-card-value" style={{ fontSize: "1rem" }}>
                {gatewayMetrics.failover_count}
              </div>
              <div className="metric-card-label">Failovers</div>
            </div>
            <div className="metric-card">
              <div className="metric-card-value" style={{ fontSize: "1rem" }}>
                {gatewayMetrics.provider_success_rate}%
              </div>
              <div className="metric-card-label">Success Rate</div>
            </div>
            <div className="metric-card">
              <div className="metric-card-value" style={{ fontSize: "1rem" }}>
                {gatewayMetrics.failed_requests}
              </div>
              <div className="metric-card-label">Failed Requests</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
