import React from "react";
import type { AuditEntry } from "../../lib/safety/policy-engine";
import type { Alert } from "./AlertsPanel";
import type { RecoveryAction } from "./RecoveryActions";

interface ExportReportProps {
  auditEntries: AuditEntry[];
  alerts: Alert[];
  recoveryActions: RecoveryAction[];
  complianceProfile: string;
  onExportJSON: () => void;
  onExportPDF: () => void;
}

export const ExportReport: React.FC<ExportReportProps> = ({
  auditEntries, alerts, recoveryActions, complianceProfile, onExportJSON, onExportPDF,
}) => {
  const summary = {
    totalAuditEntries: auditEntries.length,
    totalAlerts: alerts.length,
    criticalAlerts: alerts.filter((a) => a.severity === "critical").length,
    unacknowledgedAlerts: alerts.filter((a) => !a.acknowledged).length,
    pendingRecovery: recoveryActions.filter((a) => a.status === "pending").length,
    completedRecovery: recoveryActions.filter((a) => a.status === "completed").length,
    failedRecovery: recoveryActions.filter((a) => a.status === "failed").length,
    complianceProfile,
    reportGenerated: new Date().toISOString(),
  };

  return (
    <div className="glass-panel" style={{ padding: 16 }}>
      <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: 12 }}>Compliance Report</div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
        {Object.entries(summary).map(([key, val]) => (
          <div key={key} style={{ padding: "6px 10px", borderRadius: 6, background: "rgba(0,0,0,0.03)", fontSize: "0.75rem" }}>
            <span style={{ color: "#9ca3af", textTransform: "capitalize" }}>{key.replace(/([A-Z])/g, " $1").trim()}: </span>
            <span style={{ fontWeight: 600 }}>{String(val)}</span>
          </div>
        ))}
      </div>

      <div style={{ fontSize: "0.7rem", color: "#9ca3af", marginBottom: 12 }}>
        Data retained for audit: {alerts.length} alerts, {auditEntries.length} decisions, {recoveryActions.length} recovery actions
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={onExportJSON} style={exportButtonStyle}>Export JSON</button>
        <button onClick={onExportPDF} style={{ ...exportButtonStyle, background: "#8b5cf6", color: "white" }}>Export PDF</button>
      </div>
    </div>
  );
};

const exportButtonStyle: React.CSSProperties = {
  flex: 1, padding: "8px 16px", fontSize: "0.75rem", fontWeight: 600,
  border: "none", borderRadius: 6, background: "#3b82f6", color: "white",
  cursor: "pointer", transition: "all 0.1s ease-out",
};
