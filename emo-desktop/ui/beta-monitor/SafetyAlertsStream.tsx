import React from "react";

export interface SafetyAlert {
  id: string;
  type: "injection" | "drift" | "override" | "violation";
  severity: "low" | "medium" | "high" | "critical";
  message: string;
  timestamp: number;
}

interface SafetyAlertsStreamProps {
  alerts: SafetyAlert[];
  onClear?: () => void;
}

const severityColors: Record<string, { bg: string; text: string; border: string }> = {
  low: { bg: "rgba(34,197,94,0.1)", text: "#22c55e", border: "rgba(34,197,94,0.3)" },
  medium: { bg: "rgba(245,158,11,0.1)", text: "#f59e0b", border: "rgba(245,158,11,0.3)" },
  high: { bg: "rgba(239,68,68,0.1)", text: "#ef4444", border: "rgba(239,68,68,0.3)" },
  critical: { bg: "rgba(220,38,38,0.15)", text: "#dc2626", border: "rgba(220,38,38,0.5)" },
};

const typeIcons: Record<string, string> = {
  injection: "⚡",
  drift: "↗",
  override: "🛑",
  violation: "⚠",
};

function formatAlertTime(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 5000) return "now";
  if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
  return `${Math.floor(diff / 60000)}m ago`;
}

export const SafetyAlertsStream: React.FC<SafetyAlertsStreamProps> = ({ alerts, onClear }) => {
  const displayAlerts = alerts.slice(-50).reverse();
  return (
    <div className="glass-panel" style={{ padding: 16, maxHeight: 400, display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Safety Alerts</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>{alerts.length} total</span>
          {onClear && (
            <button onClick={onClear} style={{ fontSize: "0.7rem", border: "none", background: "none", color: "#6b7280", cursor: "pointer", textDecoration: "underline" }}>
              Clear
            </button>
          )}
        </div>
      </div>
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
        {displayAlerts.length === 0 ? (
          <div style={{ textAlign: "center", padding: 24, color: "#9ca3af", fontSize: "0.85rem" }}>
            No alerts — system nominal
          </div>
        ) : (
          displayAlerts.map((alert) => {
            const colors = severityColors[alert.severity] || severityColors.low;
            return (
              <div
                key={alert.id}
                style={{
                  padding: "8px 10px",
                  borderRadius: 6,
                  background: colors.bg,
                  border: `1px solid ${colors.border}`,
                  fontSize: "0.78rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 600, color: colors.text }}>
                    {typeIcons[alert.type] || "•"} {alert.type.toUpperCase()}
                  </span>
                  <span style={{ color: "#6b7280", fontSize: "0.7rem" }}>{formatAlertTime(alert.timestamp)}</span>
                </div>
                <div style={{ marginTop: 2, color: "#374151" }}>{alert.message}</div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
