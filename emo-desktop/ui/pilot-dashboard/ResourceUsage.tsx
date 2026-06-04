import React from "react";

interface ResourceMetrics {
  cpuPercent: number;
  memoryMb: number;
  memoryPercent: number;
  tokenUsage: number;
  tokenLimit: number;
  networkRequestsPerMin: number;
  activeSessions: number;
}

interface ResourceUsageProps {
  resources: ResourceMetrics;
}

const barColor = (pct: number): string => {
  if (pct < 50) return "#22c55e";
  if (pct < 80) return "#f59e0b";
  return "#ef4444";
};

export const ResourceUsage: React.FC<ResourceUsageProps> = ({ resources }) => {
  const bars = [
    { label: "CPU", value: resources.cpuPercent, unit: "%" },
    { label: "Memory", value: resources.memoryPercent, unit: "%" },
    { label: "Tokens", value: (resources.tokenUsage / resources.tokenLimit) * 100, unit: "%" },
  ];

  return (
    <div className="glass-panel" style={{ padding: 16 }}>
      <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: 12 }}>Resource Usage</div>

      {bars.map((bar) => (
        <div key={bar.label} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem", marginBottom: 4 }}>
            <span style={{ color: "#6b7280" }}>{bar.label}</span>
            <span style={{ fontWeight: 600, color: barColor(bar.value) }}>
              {bar.value.toFixed(1)}{bar.unit}
            </span>
          </div>
          <div style={{ height: 8, borderRadius: 4, background: "#e5e7eb", overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 4,
              width: `${Math.min(100, bar.value)}%`,
              background: barColor(bar.value),
              transition: "width 0.3s ease-out",
            }} />
          </div>
        </div>
      ))}

      <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: "0.7rem", color: "#9ca3af" }}>
        <span>Memory: {(resources.memoryMb / 1024).toFixed(1)} GB</span>
        <span>Tokens: {resources.tokenUsage.toLocaleString()} / {resources.tokenLimit.toLocaleString()}</span>
        <span>Network: {resources.networkRequestsPerMin}/min</span>
        <span>Sessions: {resources.activeSessions}</span>
      </div>
    </div>
  );
};
