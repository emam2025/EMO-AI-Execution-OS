import React from "react";

export interface FeedbackItem {
  id: string;
  type: string;
  status: string;
  summary: string;
  timestamp: number;
  companyHash: string;
}

interface FeedbackQueueProps {
  items: FeedbackItem[];
  filter: string;
  onFilterChange: (filter: string) => void;
  onStatusUpdate: (id: string, status: string) => void;
  onExportCsv: () => void;
}

const statusColors: Record<string, string> = {
  new: "#3b82f6",
  acknowledged: "#f59e0b",
  triaged: "#8b5cf6",
  resolved: "#22c55e",
  dismissed: "#6b7280",
};

function formatFeedbackTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export const FeedbackQueue: React.FC<FeedbackQueueProps> = ({ items, filter, onFilterChange, onStatusUpdate, onExportCsv }) => {
  const filtered = filter ? items.filter((i) => i.type === filter || i.status === filter) : items;
  const types = Array.from(new Set(items.map((i) => i.type)));
  return (
    <div className="glass-panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Feedback Queue</h3>
        <button
          onClick={onExportCsv}
          style={{
            padding: "4px 12px",
            fontSize: "0.75rem",
            border: "1px solid #d1d5db",
            borderRadius: 4,
            background: "#fff",
            cursor: "pointer",
          }}
        >
          Export CSV
        </button>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <button
          onClick={() => onFilterChange("")}
          style={{
            padding: "2px 10px",
            fontSize: "0.7rem",
            borderRadius: 12,
            border: `1px solid ${filter === "" ? "#3b82f6" : "#d1d5db"}`,
            background: filter === "" ? "#3b82f6" : "transparent",
            color: filter === "" ? "#fff" : "#374151",
            cursor: "pointer",
          }}
        >
          All
        </button>
        {types.map((t) => (
          <button
            key={t}
            onClick={() => onFilterChange(filter === t ? "" : t)}
            style={{
              padding: "2px 10px",
              fontSize: "0.7rem",
              borderRadius: 12,
              border: `1px solid ${filter === t ? "#3b82f6" : "#d1d5db"}`,
              background: filter === t ? "#3b82f6" : "transparent",
              color: filter === t ? "#fff" : "#374151",
              cursor: "pointer",
            }}
          >
            {t}
          </button>
        ))}
      </div>
      <div style={{ maxHeight: 300, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
        {filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: 24, color: "#9ca3af", fontSize: "0.85rem" }}>
            No feedback items
          </div>
        ) : (
          filtered.map((item) => (
            <div
              key={item.id}
              style={{
                padding: "8px 10px",
                borderRadius: 6,
                border: "1px solid rgba(0,0,0,0.06)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: "0.78rem",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{ fontWeight: 600, color: "#374151" }}>{item.type}</span>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "1px 6px",
                      borderRadius: 8,
                      fontSize: "0.65rem",
                      fontWeight: 600,
                      background: statusColors[item.status] || "#6b7280",
                      color: "#fff",
                    }}
                  >
                    {item.status}
                  </span>
                </div>
                <div style={{ color: "#6b7280", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {item.summary}
                </div>
                <div style={{ color: "#9ca3af", fontSize: "0.7rem", marginTop: 2 }}>
                  {formatFeedbackTime(item.timestamp)} · {item.companyHash.slice(0, 8)}
                </div>
              </div>
              <select
                value={item.status}
                onChange={(e) => onStatusUpdate(item.id, e.target.value)}
                style={{
                  marginLeft: 8,
                  fontSize: "0.7rem",
                  padding: "2px 4px",
                  border: "1px solid #d1d5db",
                  borderRadius: 4,
                  background: "#fff",
                }}
              >
                <option value="new">new</option>
                <option value="acknowledged">acknowledged</option>
                <option value="triaged">triaged</option>
                <option value="resolved">resolved</option>
                <option value="dismissed">dismissed</option>
              </select>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
