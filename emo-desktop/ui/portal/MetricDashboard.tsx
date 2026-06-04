import React from "react";

export interface MetricSummary {
  name: string;
  avg: number;
  min: number;
  max: number;
  count: number;
  stdDev: number;
}

export interface AnomalyAlert {
  metricName: string;
  date: string;
  value: number;
  severity: "low" | "medium" | "high";
  zScore: number;
}

interface MetricDashboardProps {
  metrics: MetricSummary[];
  anomalies: AnomalyAlert[];
  onRefresh: () => void;
}

const severityColors: Record<string, string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#3b82f6",
};

export const MetricDashboard: React.FC<MetricDashboardProps> = ({ metrics, anomalies, onRefresh }) => {
  return (
    <div className="glass-panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(0,0,0,0.06)", fontWeight: 600, fontSize: "0.85rem", display: "flex", alignItems: "center", gap: 8 }}>
        <span>Metric Dashboard</span>
        <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "#9ca3af" }}>{metrics.length} metrics</span>
        <button onClick={onRefresh} style={refreshButtonStyle}>Refresh</button>
      </div>

      {anomalies.length > 0 && (
        <div style={{ padding: "8px 12px", background: "#fef2f2", borderBottom: "1px solid rgba(239,68,68,0.2)" }}>
          <div style={{ fontWeight: 600, fontSize: "0.75rem", color: "#ef4444", marginBottom: 4 }}>Anomalies Detected ({anomalies.length})</div>
          {anomalies.slice(0, 3).map((a, i) => (
            <div key={i} style={{ fontSize: "0.7rem", color: "#6b7280", marginBottom: 2 }}>
              <span style={{ color: severityColors[a.severity], fontWeight: 600 }}>●</span> {a.metricName}: {a.value.toFixed(2)} (z={a.zScore.toFixed(2)})
            </div>
          ))}
        </div>
      )}

      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {metrics.length === 0 && (
          <p style={{ padding: "24px 8px", textAlign: "center", color: "#9ca3af", fontSize: "0.8rem" }}>No metrics collected yet</p>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          {metrics.map((m) => {
            const barColor = m.stdDev > m.avg * 0.5 ? "#ef4444" : m.stdDev > m.avg * 0.25 ? "#f59e0b" : "#22c55e";
            return (
              <div key={m.name} style={metricCardStyle}>
                <div style={{ fontSize: "0.65rem", color: "#9ca3af", marginBottom: 2, textTransform: "uppercase", letterSpacing: "0.03em" }}>{m.name}</div>
                <div style={{ fontWeight: 600, fontSize: "0.9rem", marginBottom: 4 }}>{m.avg.toFixed(1)}</div>
                <div style={{ height: 4, borderRadius: 2, background: "#e5e7eb", marginBottom: 4 }}>
                  <div style={{ height: "100%", borderRadius: 2, background: barColor, width: `${Math.min(100, (m.avg / (m.max || 1)) * 100)}%` }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.65rem", color: "#9ca3af" }}>
                  <span>min: {m.min.toFixed(1)}</span>
                  <span>max: {m.max.toFixed(1)}</span>
                </div>
                <div style={{ fontSize: "0.65rem", color: "#9ca3af" }}>σ = {m.stdDev.toFixed(2)} · n = {m.count}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

const metricCardStyle: React.CSSProperties = {
  padding: "8px 10px", borderRadius: 6, background: "rgba(0,0,0,0.03)",
};

const refreshButtonStyle: React.CSSProperties = {
  padding: "4px 10px", fontSize: "0.7rem", border: "1px solid #3b82f6",
  borderRadius: 4, background: "#3b82f6", color: "white", cursor: "pointer", fontWeight: 500,
};
