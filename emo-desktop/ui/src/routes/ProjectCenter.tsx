import React from "react";

export const ProjectCenter: React.FC = () => {
  const stats = [
    { label: "Active Sessions", value: "--" },
    { label: "Total Intents", value: "--" },
    { label: "Completed Tasks", value: "--" },
    { label: "Failed Tasks", value: "--" },
  ];

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          Project Center
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Sessions, intents, and execution history — coming in a future update
        </p>
      </div>

      <div className="glass-panel" style={{ padding: 16 }}>
        <div className="section-header">Session Overview</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {stats.map((s) => (
            <div key={s.label} className="metric-card">
              <div className="metric-card-value" style={{ fontSize: "1.3rem" }}>{s.value}</div>
              <div className="metric-card-label">{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="glass-panel" style={{ padding: 16, flex: 1 }}>
        <div className="section-header">Recent Activity</div>
        <div style={{ padding: 32, textAlign: "center" }}>
          <p style={{ color: "#9ca3af", fontSize: "0.85rem", marginBottom: 8 }}>▤</p>
          <p style={{ color: "#9ca3af", fontSize: "0.85rem" }}>
            Session tracking will be available after the R2 Memory OS integration.
          </p>
          <p style={{ color: "#d0d5dd", fontSize: "0.75rem", marginTop: 4 }}>
            Phase P1 — IPC contract readiness confirmed
          </p>
        </div>
      </div>
    </div>
  );
};
