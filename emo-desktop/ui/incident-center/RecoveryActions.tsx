import React from "react";

export type RecoveryStatus = "pending" | "in_progress" | "completed" | "failed" | "rolled_back";

export interface RecoveryAction {
  id: string;
  alertId: string;
  description: string;
  status: RecoveryStatus;
  initiatedBy: string;
  approvedBy?: string[];
  timestamp: number;
  completedAt?: number;
  notes?: string;
}

const statusColors: Record<RecoveryStatus, string> = {
  pending: "#9ca3af",
  in_progress: "#3b82f6",
  completed: "#22c55e",
  failed: "#ef4444",
  rolled_back: "#f59e0b",
};

interface RecoveryActionsProps {
  actions: RecoveryAction[];
  onExecute: (action: RecoveryAction) => void;
  onRollback: (action: RecoveryAction) => void;
}

export const RecoveryActions: React.FC<RecoveryActionsProps> = ({ actions, onExecute, onRollback }) => {
  return (
    <div className="glass-panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(0,0,0,0.06)", fontWeight: 600, fontSize: "0.85rem" }}>
        Recovery Actions
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {actions.length === 0 && (
          <p style={{ padding: "24px 8px", textAlign: "center", color: "#9ca3af", fontSize: "0.8rem" }}>No recovery actions recorded</p>
        )}
        {actions.map((action) => (
          <div
            key={action.id}
            style={{
              padding: "10px 12px", marginBottom: 6, borderRadius: 8,
              border: "1px solid rgba(0,0,0,0.06)", background: "white",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{
                padding: "2px 8px", borderRadius: 4, fontSize: "0.65rem", fontWeight: 600,
                textTransform: "uppercase", letterSpacing: "0.03em",
                background: `${statusColors[action.status]}20`,
                color: statusColors[action.status],
              }}>
                {action.status.replace("_", " ")}
              </span>
              <span style={{ fontWeight: 500, fontSize: "0.8rem" }}>{action.description}</span>
            </div>
            <div style={{ fontSize: "0.7rem", color: "#9ca3af", marginBottom: 4 }}>
              By: {action.initiatedBy} · {new Date(action.timestamp).toLocaleString()}
              {action.approvedBy && action.approvedBy.length > 0 && ` · Approved by: ${action.approvedBy.join(", ")}`}
            </div>
            {action.notes && <p style={{ margin: "2px 0 0", fontSize: "0.75rem", color: "#6b7280", fontStyle: "italic" }}>{action.notes}</p>}
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              {action.status === "pending" && (
                <button onClick={() => onExecute(action)} style={actionButtonStyle}>Execute</button>
              )}
              {action.status === "completed" && (
                <button onClick={() => onRollback(action)} style={{ ...actionButtonStyle, background: "#f59e0b", color: "white" }}>Rollback</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const actionButtonStyle: React.CSSProperties = {
  padding: "4px 10px", fontSize: "0.7rem", border: "none",
  borderRadius: 4, background: "#3b82f6", color: "white", cursor: "pointer", fontWeight: 500,
  transition: "all 0.1s ease-out",
};
