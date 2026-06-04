import React from "react";

export type AlertSeverity = "critical" | "high" | "medium" | "low" | "info";

export interface Alert {
  id: string;
  timestamp: number;
  severity: AlertSeverity;
  title: string;
  description: string;
  source: string;
  acknowledged: boolean;
  action?: string;
}

const severityColors: Record<AlertSeverity, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#f59e0b",
  low: "#22c55e",
  info: "#3b82f6",
};

interface AlertsPanelProps {
  alerts: Alert[];
  onAcknowledge: (id: string) => void;
  onTakeAction: (alert: Alert) => void;
}

export const AlertsPanel: React.FC<AlertsPanelProps> = ({ alerts, onAcknowledge, onTakeAction }) => {
  const sorted = [...alerts].sort((a, b) => {
    const sevOrder: Record<AlertSeverity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    return (sevOrder[a.severity] ?? 5) - (sevOrder[b.severity] ?? 5);
  });

  return (
    <div className="glass-panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(0,0,0,0.06)", fontWeight: 600, fontSize: "0.85rem", display: "flex", alignItems: "center", gap: 8 }}>
        <span>Alerts & Anomalies</span>
        <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "#9ca3af" }}>{alerts.filter((a) => !a.acknowledged).length} unacknowledged</span>
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {sorted.length === 0 && (
          <p style={{ padding: "24px 8px", textAlign: "center", color: "#9ca3af", fontSize: "0.8rem" }}>No alerts — system nominal</p>
        )}
        {sorted.map((alert) => (
          <div
            key={alert.id}
            style={{
              padding: "10px 12px", marginBottom: 6, borderRadius: 8,
              border: "1px solid rgba(0,0,0,0.06)",
              background: alert.acknowledged ? "rgba(0,0,0,0.02)" : "white",
              opacity: alert.acknowledged ? 0.6 : 1,
              transition: "all 0.12s ease-out",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: severityColors[alert.severity], flexShrink: 0 }} />
              <span style={{ fontWeight: 600, fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.03em", color: severityColors[alert.severity] }}>
                {alert.severity}
              </span>
              <span style={{ fontWeight: 500, fontSize: "0.8rem" }}>{alert.title}</span>
              <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "#9ca3af" }}>
                {new Date(alert.timestamp).toLocaleString()}
              </span>
            </div>
            <p style={{ margin: "2px 0 0 16px", fontSize: "0.75rem", color: "#6b7280" }}>{alert.description}</p>
            <div style={{ display: "flex", gap: 6, marginTop: 6, marginLeft: 16 }}>
              {!alert.acknowledged && (
                <button onClick={() => onAcknowledge(alert.id)} style={smallButtonStyle}>Acknowledge</button>
              )}
              {alert.action && (
                <button onClick={() => onTakeAction(alert)} style={{ ...smallButtonStyle, background: "#3b82f6", color: "white" }}>
                  {alert.action}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const smallButtonStyle: React.CSSProperties = {
  padding: "4px 10px", fontSize: "0.7rem", border: "1px solid rgba(0,0,0,0.1)",
  borderRadius: 4, background: "#f3f4f6", cursor: "pointer", fontWeight: 500,
  transition: "all 0.1s ease-out",
};
