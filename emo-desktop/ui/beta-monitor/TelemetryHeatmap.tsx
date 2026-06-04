import React from "react";

export interface TelemetryCell {
  metric: string;
  category: string;
  value: number;
  maxValue: number;
  status: "success" | "warning" | "critical";
}

interface TelemetryHeatmapProps {
  cells: TelemetryCell[];
}

const statusGradients: Record<string, string> = {
  success: "linear-gradient(135deg, #22c55e, #16a34a)",
  warning: "linear-gradient(135deg, #f59e0b, #d97706)",
  critical: "linear-gradient(135deg, #ef4444, #dc2626)",
};

export const TelemetryHeatmap: React.FC<TelemetryHeatmapProps> = ({ cells }) => {
  const grouped = new Map<string, TelemetryCell[]>();
  for (const cell of cells) {
    const existing = grouped.get(cell.category);
    if (existing) {
      existing.push(cell);
    } else {
      grouped.set(cell.category, [cell]);
    }
  }
  const categories = Array.from(grouped.keys());
  return (
    <div className="glass-panel" style={{ padding: 16 }}>
      <h3 style={{ margin: "0 0 12px", fontSize: "1rem", fontWeight: 600 }}>Telemetry Heatmap</h3>
      {categories.length === 0 ? (
        <div style={{ textAlign: "center", padding: 24, color: "#9ca3af", fontSize: "0.85rem" }}>
          No telemetry data collected
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {categories.map((category) => {
            const catCells = grouped.get(category)!;
            return (
              <div key={category}>
                <div style={{ fontSize: "0.75rem", fontWeight: 500, color: "#6b7280", marginBottom: 6, textTransform: "capitalize" }}>
                  {category.replace(/_/g, " ")}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(catCells.length, 4)}, 1fr)`, gap: 6 }}>
                  {catCells.map((cell, idx) => {
                    const intensity = Math.min(cell.value / Math.max(cell.maxValue, 1), 1);
                    return (
                      <div
                        key={`${cell.metric}-${idx}`}
                        style={{
                          padding: "8px 6px",
                          borderRadius: 6,
                          background: statusGradients[cell.status] || statusGradients.success,
                          opacity: 0.3 + intensity * 0.7,
                          textAlign: "center",
                          color: "#fff",
                          fontSize: "0.72rem",
                          fontWeight: 500,
                        }}
                        title={`${cell.metric}: ${cell.value} / ${cell.maxValue}`}
                      >
                        <div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {cell.metric}
                        </div>
                        <div style={{ fontSize: "0.9rem", fontWeight: 700, marginTop: 2 }}>
                          {cell.value}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <div style={{ marginTop: 12, display: "flex", gap: 12, fontSize: "0.7rem", color: "#6b7280" }}>
        <span><span style={{ color: "#22c55e" }}>■</span> Success</span>
        <span><span style={{ color: "#f59e0b" }}>■</span> Warning</span>
        <span><span style={{ color: "#ef4444" }}>■</span> Critical</span>
      </div>
    </div>
  );
};
