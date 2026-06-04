import React from "react";

interface CompanyHealthProps {
  companyId: string;
  agentCount: number;
  healthyAgents: number;
  taskSuccessRate: number;
  avgLatencyMs: number;
  uptimePercent: number;
  lastReportDate: string;
  errorCount: number;
}

const healthColor = (rate: number): string => {
  if (rate >= 0.95) return "#22c55e";
  if (rate >= 0.8) return "#f59e0b";
  return "#ef4444";
};

export const CompanyHealth: React.FC<CompanyHealthProps> = ({
  companyId, agentCount, healthyAgents, taskSuccessRate,
  avgLatencyMs, uptimePercent, lastReportDate, errorCount,
}) => {
  const score = Math.round(taskSuccessRate * 100);
  const color = healthColor(taskSuccessRate);

  return (
    <div className="glass-panel" style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div style={{
          width: 48, height: 48, borderRadius: "50%",
          background: `conic-gradient(${color} ${score}%, #e5e7eb ${score}%)`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontWeight: 700, fontSize: "0.85rem", color,
        }}>
          {score}%
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: "0.85rem" }}>Company {companyId.slice(0, 8)}</div>
          <div style={{ fontSize: "0.7rem", color: "#9ca3af" }}>Last report: {lastReportDate}</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {[
          { label: "Agents", value: `${healthyAgents}/${agentCount}`, color: healthyAgents === agentCount ? "#22c55e" : "#f59e0b" },
          { label: "Success Rate", value: `${score}%`, color },
          { label: "Avg Latency", value: `${avgLatencyMs.toFixed(0)}ms`, color: avgLatencyMs < 500 ? "#22c55e" : "#f59e0b" },
          { label: "Uptime", value: `${uptimePercent.toFixed(1)}%`, color: uptimePercent > 99 ? "#22c55e" : "#f59e0b" },
          { label: "Errors (24h)", value: String(errorCount), color: errorCount < 5 ? "#22c55e" : "#ef4444" },
        ].map((m) => (
          <div key={m.label} style={{ padding: "6px 10px", borderRadius: 6, background: "rgba(0,0,0,0.03)" }}>
            <div style={{ fontSize: "0.65rem", color: "#9ca3af", marginBottom: 2 }}>{m.label}</div>
            <div style={{ fontWeight: 600, fontSize: "0.85rem", color: m.color }}>{m.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
};
