import React from "react";

type FeedbackStatus = "new" | "reviewed" | "in_progress" | "resolved" | "dismissed";

interface FeedbackItem {
  id: string;
  companyId: string;
  submittedAt: number;
  category: string;
  summary: string;
  status: FeedbackStatus;
  environment: string;
  hasTrace: boolean;
}

interface FeedbackInboxProps {
  items: FeedbackItem[];
  onStatusChange: (id: string, status: FeedbackStatus) => void;
  onViewDetails: (item: FeedbackItem) => void;
}

const statusColors: Record<FeedbackStatus, string> = {
  new: "#3b82f6",
  reviewed: "#f59e0b",
  in_progress: "#8b5cf6",
  resolved: "#22c55e",
  dismissed: "#9ca3af",
};

export const FeedbackInbox: React.FC<FeedbackInboxProps> = ({ items, onStatusChange, onViewDetails }) => {
  const sorted = [...items].sort((a, b) => b.submittedAt - a.submittedAt);

  return (
    <div className="glass-panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(0,0,0,0.06)", display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: "0.85rem" }}>
        <span>Feedback Inbox</span>
        <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "#3b82f6" }}>{items.filter((i) => i.status === "new").length} new</span>
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {items.length === 0 && (
          <p style={{ padding: "24px 8px", textAlign: "center", color: "#9ca3af", fontSize: "0.8rem" }}>No feedback received yet</p>
        )}
        {sorted.map((item) => (
          <div
            key={item.id}
            style={{
              padding: "10px 12px", marginBottom: 6, borderRadius: 8,
              border: "1px solid rgba(0,0,0,0.06)", background: item.status === "new" ? "#f0f7ff" : "white",
              cursor: "pointer", transition: "all 0.1s ease-out",
            }}
            onClick={() => onViewDetails(item)}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <span style={{
                padding: "2px 6px", borderRadius: 4, fontSize: "0.6rem", fontWeight: 600,
                background: `${statusColors[item.status]}20`, color: statusColors[item.status],
                textTransform: "uppercase",
              }}>
                {item.status.replace("_", " ")}
              </span>
              <span style={{ fontWeight: 500, fontSize: "0.8rem" }}>{item.summary}</span>
              <span style={{ marginLeft: "auto", fontSize: "0.65rem", color: "#9ca3af" }}>
                {new Date(item.submittedAt).toLocaleDateString()}
              </span>
            </div>
            <div style={{ display: "flex", gap: 8, fontSize: "0.65rem", color: "#9ca3af" }}>
              <span>Category: {item.category}</span>
              <span>Env: {item.environment}</span>
              {item.hasTrace && <span style={{ color: "#3b82f6" }}>Trace attached</span>}
            </div>
            {item.status === "new" && (
              <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
                <button onClick={(e) => { e.stopPropagation(); onStatusChange(item.id, "in_progress"); }} style={smallBtn}>Acknowledge</button>
                <button onClick={(e) => { e.stopPropagation(); onStatusChange(item.id, "dismissed"); }} style={{ ...smallBtn, background: "#f3f4f6", color: "#6b7280" }}>Dismiss</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

const smallBtn: React.CSSProperties = {
  padding: "3px 8px", fontSize: "0.65rem", fontWeight: 500,
  border: "none", borderRadius: 4, background: "#3b82f6", color: "white",
  cursor: "pointer",
};
