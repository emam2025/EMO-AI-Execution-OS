import React from "react";
import { StatusBadge } from "../../styles/design-system/status-badge";

type Route = "dashboard" | "projects" | "agents" | "knowledge" | "skills" | "workflows" | "runtime-monitor" | "ai-gateway" | "settings";

interface AIGatewayProps {
  onNavigate?: (route: Route) => void;
}

export const AIGateway: React.FC<AIGatewayProps> = ({ onNavigate }) => {
  const [routingStatus] = React.useState<{
    failover_ready: boolean;
    active_routes: string[];
    routing_table: { provider: string; status: string; latency_ms: number; cost_per_1k: number }[];
    cost_tracking: { total_spent_usd: number; budget_limit_usd: number };
  } | null>(null);
  const [gatewayMetrics] = React.useState<{
    total_requests: number;
    avg_latency_ms: number;
    failover_count: number;
    rate_limited_count: number;
  } | null>(null);

  const providers = routingStatus?.routing_table ?? [];
  const activeRoutes = routingStatus?.active_routes ?? [];

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          AI Gateway
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Model management, live routing, failover status, and cost tracking
        </p>
      </div>

      <div className="glass-panel" style={{ padding: 16, display: "flex", alignItems: "center", gap: 20 }}>
        <div>
          <div className="section-header" style={{ marginBottom: 4 }}>Failover Readiness</div>
          <StatusBadge state={routingStatus?.failover_ready ? "active" : "down"} label={routingStatus?.failover_ready ? "Ready" : "Not Ready"} />
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

      <div className="glass-panel" style={{ padding: 16, flex: 1 }}>
        <div className="section-header">Routing Table</div>
        {providers.length === 0 && (
          <p style={{ color: "#9ca3af", fontSize: "0.85rem", padding: 24, textAlign: "center" }}>
            No providers configured.{onNavigate ? (
              <span> Go to <a href="#" onClick={(e) => { e.preventDefault(); onNavigate("settings"); }} style={{ color: "#2563eb", textDecoration: "underline", cursor: "pointer" }}>Settings → Providers</a> to add API keys.</span>
            ) : " Go to Settings to add API keys."}
          </p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {providers.map((entry) => (
            <div key={entry.provider} className="smooth-enter" style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "10px 14px", borderRadius: 8,
              background: "rgba(255,255,255,0.5)", border: "1px solid rgba(0,0,0,0.04)",
            }}>
              <span style={{ fontWeight: 600, fontSize: "0.85rem", width: 120 }}>{entry.provider}</span>
              <StatusBadge state={entry.status === "active" ? "active" : entry.status === "rate_limited" ? "rate_limited" : "down"} label={entry.status} size="sm" />
              <span style={{ fontSize: "0.75rem", color: "#9ca3af", marginLeft: "auto" }}>
                {entry.latency_ms}ms · ${entry.cost_per_1k.toFixed(4)}/1k
              </span>
            </div>
          ))}
        </div>
      </div>

      {gatewayMetrics && (
        <div className="glass-panel" style={{ padding: 16 }}>
          <div className="section-header">Aggregated Metrics</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            <div className="metric-card">
              <div className="metric-card-value">{gatewayMetrics.total_requests}</div>
              <div className="metric-card-label">Total Requests</div>
            </div>
            <div className="metric-card">
              <div className="metric-card-value">{gatewayMetrics.avg_latency_ms}ms</div>
              <div className="metric-card-label">Avg Latency</div>
            </div>
            <div className="metric-card">
              <div className="metric-card-value">{gatewayMetrics.failover_count}</div>
              <div className="metric-card-label">Failovers</div>
            </div>
            <div className="metric-card">
              <div className="metric-card-value">{gatewayMetrics.rate_limited_count}</div>
              <div className="metric-card-label">Rate Limited</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
