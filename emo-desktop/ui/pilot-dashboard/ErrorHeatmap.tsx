import React from "react";

interface ErrorBucket {
  label: string;
  count: number;
  severity: "low" | "medium" | "high" | "critical";
}

interface ErrorHeatmapProps {
  data: ErrorBucket[];
  totalErrors: number;
}

const severityHeat: Record<string, string> = {
  low: "rgba(34,197,94,0.15)",
  medium: "rgba(245,158,11,0.2)",
  high: "rgba(239,68,68,0.3)",
  critical: "rgba(220,38,38,0.5)",
};

const maxCount = (buckets: ErrorBucket[]): number => {
  return Math.max(1, ...buckets.map((b) => b.count));
};

export const ErrorHeatmap: React.FC<ErrorHeatmapProps> = ({ data, totalErrors }) => {
  const max = maxCount(data);

  return (
    <div className="glass-panel" style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>Error Heatmap</span>
        <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: totalErrors > 0 ? "#ef4444" : "#22c55e", fontWeight: 600 }}>
          {totalErrors > 0 ? `${totalErrors} errors` : "No errors"}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {data.length === 0 && (
          <p style={{ padding: "16px 0", textAlign: "center", color: "#9ca3af", fontSize: "0.75rem" }}>No error data available</p>
        )}
        {data.map((bucket) => {
          const width = (bucket.count / max) * 100;
          return (
            <div key={bucket.label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.7rem" }}>
              <span style={{ width: 100, color: "#6b7280", textAlign: "right", overflow: "hidden", textOverflow: "ellipsis" }}>
                {bucket.label}
              </span>
              <div style={{ flex: 1, height: 20, borderRadius: 4, background: "rgba(0,0,0,0.04)", overflow: "hidden" }}>
                <div style={{
                  height: "100%", borderRadius: 4,
                  width: `${Math.max(2, width)}%`,
                  background: severityHeat[bucket.severity] || "rgba(0,0,0,0.1)",
                  transition: "width 0.3s ease-out",
                  display: "flex", alignItems: "center", paddingLeft: 6,
                  fontWeight: 600, color: bucket.severity === "critical" ? "white" : "#374151",
                }}>
                  {bucket.count}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
