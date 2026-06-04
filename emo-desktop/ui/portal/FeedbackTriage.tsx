import React from "react";

export type FeedbackCategory = "bug" | "performance" | "feature" | "security" | "ux" | "other";
export type FeedbackStatus = "new" | "reviewing" | "triaged" | "resolved" | "dismissed";
export type FeedbackPriority = "low" | "medium" | "high" | "critical";

export interface FeedbackItem {
  id: string;
  timestamp: number;
  category: FeedbackCategory;
  status: FeedbackStatus;
  title: string;
  description: string;
  source: string;
  priority: FeedbackPriority;
}

interface FeedbackTriageProps {
  items: FeedbackItem[];
  onUpdateStatus: (id: string, status: FeedbackStatus) => void;
  onFilterChange: (category: FeedbackCategory | "all") => void;
  onSeverityFilterChange: (priority: FeedbackPriority | "all") => void;
  activeFilter: FeedbackCategory | "all";
  activeSeverityFilter: FeedbackPriority | "all";
}

const categoryColors: Record<FeedbackCategory, string> = {
  bug: "#ef4444",
  performance: "#f59e0b",
  feature: "#3b82f6",
  security: "#8b5cf6",
  ux: "#22c55e",
  other: "#9ca3af",
};

const statusColors: Record<FeedbackStatus, string> = {
  new: "#3b82f6",
  reviewing: "#f59e0b",
  triaged: "#8b5cf6",
  resolved: "#22c55e",
  dismissed: "#9ca3af",
};

const priorityColors: Record<FeedbackPriority, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#f59e0b",
  low: "#22c55e",
};

const CATEGORIES: (FeedbackCategory | "all")[] = ["all", "bug", "performance", "feature", "security", "ux", "other"];
const SEVERITIES: (FeedbackPriority | "all")[] = ["all", "critical", "high", "medium", "low"];

export const FeedbackTriage: React.FC<FeedbackTriageProps> = ({
  items, onUpdateStatus, onFilterChange, onSeverityFilterChange, activeFilter, activeSeverityFilter,
}) => {
  return (
    <div className="glass-panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(0,0,0,0.06)", fontWeight: 600, fontSize: "0.85rem" }}>
        Feedback Triage
      </div>

      <div style={{ padding: "8px 12px", borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
        <div style={{ fontSize: "0.65rem", color: "#9ca3af", marginBottom: 4 }}>Category</div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => onFilterChange(cat)}
              style={{
                ...filterBtnStyle,
                background: activeFilter === cat ? "#3b82f6" : "#f3f4f6",
                color: activeFilter === cat ? "white" : "#374151",
              }}
            >
              {cat.charAt(0).toUpperCase() + cat.slice(1)}
            </button>
          ))}
        </div>
        <div style={{ fontSize: "0.65rem", color: "#9ca3af", marginBottom: 4 }}>Severity</div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {SEVERITIES.map((sev) => (
            <button
              key={sev}
              onClick={() => onSeverityFilterChange(sev)}
              style={{
                ...filterBtnStyle,
                background: activeSeverityFilter === sev ? (sev === "all" ? "#6b7280" : priorityColors[sev]) : "#f3f4f6",
                color: activeSeverityFilter === sev ? "white" : "#374151",
              }}
            >
              {sev.charAt(0).toUpperCase() + sev.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {items.length === 0 && (
          <p style={{ padding: "24px 8px", textAlign: "center", color: "#9ca3af", fontSize: "0.8rem" }}>No feedback items</p>
        )}
        {items.map((item) => (
          <div key={item.id} style={itemCardStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: categoryColors[item.category], flexShrink: 0 }} />
              <span style={{ fontSize: "0.65rem", fontWeight: 600, color: categoryColors[item.category], textTransform: "uppercase" }}>
                {item.category}
              </span>
              <span style={{
                fontSize: "0.65rem", padding: "1px 6px", borderRadius: 4,
                background: priorityColors[item.priority] + "22",
                color: priorityColors[item.priority], fontWeight: 600,
              }}>
                {item.priority}
              </span>
              <span style={{
                fontSize: "0.65rem", padding: "1px 6px", borderRadius: 4,
                background: statusColors[item.status] + "22",
                color: statusColors[item.status], fontWeight: 600,
              }}>
                {item.status}
              </span>
              <span style={{ marginLeft: "auto", fontSize: "0.65rem", color: "#9ca3af" }}>
                {new Date(item.timestamp).toLocaleString()}
              </span>
            </div>
            <div style={{ fontWeight: 500, fontSize: "0.8rem", marginBottom: 2 }}>{item.title}</div>
            <div style={{ fontSize: "0.7rem", color: "#6b7280", marginBottom: 4 }}>{item.description.slice(0, 120)}</div>
            <div style={{ display: "flex", gap: 4 }}>
              {item.status === "new" && (
                <button onClick={() => onUpdateStatus(item.id, "reviewing")} style={actionBtnStyle}>Review</button>
              )}
              {item.status === "reviewing" && (
                <button onClick={() => onUpdateStatus(item.id, "triaged")} style={{ ...actionBtnStyle, background: "#8b5cf6", color: "white" }}>
                  Triage
                </button>
              )}
              {(item.status === "triaged" || item.status === "reviewing") && (
                <button onClick={() => onUpdateStatus(item.id, "resolved")} style={{ ...actionBtnStyle, background: "#22c55e", color: "white" }}>
                  Resolve
                </button>
              )}
              {item.status !== "dismissed" && item.status !== "resolved" && (
                <button onClick={() => onUpdateStatus(item.id, "dismissed")} style={{ ...actionBtnStyle, background: "#f3f4f6", color: "#9ca3af" }}>
                  Dismiss
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const filterBtnStyle: React.CSSProperties = {
  padding: "3px 8px", fontSize: "0.65rem", border: "1px solid rgba(0,0,0,0.08)",
  borderRadius: 4, cursor: "pointer", fontWeight: 500,
};

const itemCardStyle: React.CSSProperties = {
  padding: "10px 12px", marginBottom: 6, borderRadius: 8,
  border: "1px solid rgba(0,0,0,0.06)", background: "white",
};

const actionBtnStyle: React.CSSProperties = {
  padding: "3px 8px", fontSize: "0.65rem", border: "1px solid rgba(0,0,0,0.1)",
  borderRadius: 4, cursor: "pointer", fontWeight: 500,
};
