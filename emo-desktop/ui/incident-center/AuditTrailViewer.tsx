import React, { useMemo } from "react";
import type { AuditEntry } from "../../lib/safety/policy-engine";

const decisionColors: Record<string, string> = {
  ALLOW: "#22c55e",
  DENY: "#ef4444",
  REQUIRE_APPROVAL: "#f59e0b",
  EMERGENCY_STOP: "#dc2626",
};

interface AuditTrailViewerProps {
  entries: AuditEntry[];
  maxEntries?: number;
}

export const AuditTrailViewer: React.FC<AuditTrailViewerProps> = ({ entries, maxEntries = 200 }) => {
  const display = useMemo(() => {
    return [...entries].sort((a, b) => b.timestamp - a.timestamp).slice(0, maxEntries);
  }, [entries, maxEntries]);

  return (
    <div className="glass-panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(0,0,0,0.06)", display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: "0.85rem" }}>
        <span>Audit Trail</span>
        <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "#9ca3af" }}>
          {entries.length} entries · Showing {display.length}
        </span>
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 8, fontFamily: "monospace", fontSize: "0.7rem" }}>
        {display.length === 0 && (
          <p style={{ padding: "24px 8px", textAlign: "center", color: "#9ca3af" }}>No audit entries recorded</p>
        )}
        {display.map((entry, i) => {
          const time = new Date(entry.timestamp).toISOString();
          const color = decisionColors[entry.decision] || "#6b7280";
          return (
            <div
              key={`${entry.timestamp}-${i}`}
              style={{
                padding: "6px 8px", marginBottom: 2, borderRadius: 4,
                borderLeft: `3px solid ${color}`,
                background: i % 2 === 0 ? "rgba(0,0,0,0.02)" : "transparent",
              }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ color, fontWeight: 600, textTransform: "uppercase", fontSize: "0.65rem" }}>
                  [{entry.decision}]
                </span>
                <span style={{ color: "#374151", fontWeight: 500 }}>{entry.action}</span>
                <span style={{ marginLeft: "auto", color: "#9ca3af", fontSize: "0.65rem" }}>{time}</span>
              </div>
              <p style={{ margin: "2px 0 0", color: "#6b7280", fontSize: "0.65rem" }}>
                {entry.reason} · by {entry.initiatedBy}
                {entry.approvedBy && entry.approvedBy.length > 0 && ` · approved: ${entry.approvedBy.join(", ")}`}
                {entry.riskProfile && ` · risk: ${(entry.riskProfile.riskScore * 100).toFixed(0)}%`}
              </p>
            </div>
          );
        })}
      </div>
      {entries.length > maxEntries && (
        <div style={{ padding: "8px 16px", borderTop: "1px solid rgba(0,0,0,0.06)", fontSize: "0.7rem", color: "#9ca3af", textAlign: "center" }}>
          Showing last {maxEntries} entries. Export for full history.
        </div>
      )}
    </div>
  );
};
