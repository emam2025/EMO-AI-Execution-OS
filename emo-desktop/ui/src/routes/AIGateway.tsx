import React from "react";
import { useRuntimeStore } from "../stores/runtime";
import { StatusBadge } from "../styles/design-system/status-badge";
import { EmptyState } from "../styles/design-system/empty-state";
import { LoadingSkeleton } from "../styles/design-system/loading-skeleton";
import { ErrorRecovery } from "../styles/design-system/error-recovery";

type Route = "dashboard" | "projects" | "agents" | "knowledge" | "skills" | "workflows" | "runtime-monitor" | "ai-gateway" | "settings" | "trace-explorer";

interface AIGatewayProps {
  onNavigate?: (route: Route) => void;
}

export const AIGateway: React.FC<AIGatewayProps> = ({ onNavigate }) => {
  const { routingStatus, gatewayMetrics, isConnected } = useRuntimeStore();

  if (!isConnected) {
    return <EmptyState icon="🔌" title="Not Connected" description="Connect to view AI Gateway status." action={undefined} />;
  }

  if (!routingStatus && !gatewayMetrics) {
    return <LoadingSkeleton variant="card" lines={3} />;
  }

  const providers = routingStatus?.routing_table ?? [];
  const activeRoutes = routingStatus?.active_routes ?? [];
  const failoverReady = routingStatus?.failover_ready ?? false;

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
          <StatusBadge state={failoverReady ? "active" : "down"} label={failoverReady ? "Ready" : "Not Ready"} />
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
            ${routingStatus?.cost_tracking?.total_spent_usd.toFixed(2) ?? "0.00"} / $
            {routingStatus?.cost_tracking?.budget_limit_usd.toFixed(2) ?? "100.00"}
          </span>
        </div>
      </div>

      <div className="glass-panel" style={{ padding: 16, flex: 1 }}>
        <div className="section-header">Routing Table</div>
        {providers.length === 0 && (
          <EmptyState
            icon="🔑"
            title="No Providers Configured"
            description="Add API keys in Settings to connect your AI providers."
            action={onNavigate ? { label: "Go to Settings", onClick: () => onNavigate("settings") } : undefined}
          />
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {providers.map((entry, i) => (
            <div key={entry.provider ?? i} className="smooth-enter" style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "10px 14px", borderRadius: 8,
              background: "rgba(255,255,255,0.5)", border: "1px solid rgba(0,0,0,0.04)",
            }}>
              <span style={{ fontWeight: 600, fontSize: "0.85rem", width: 120 }}>{entry.provider}</span>
              <StatusBadge
                state={entry.status === "active" ? "active" : entry.status === "rate_limited" ? "rate_limited" : "down"}
                label={entry.status} size="sm"
              />
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
