import React from "react";

export interface QueueItem {
  id: string;
  title: string;
  type: "bug" | "feature" | "feedback";
  impact: number;
  frequency: number;
  priorityScore: number;
  status: string;
  createdAt: number;
}

interface PriorityQueueViewProps {
  items: QueueItem[];
  onExportTriage: () => void;
  onUpdateStatus: (id: string, status: string) => void;
}

function scoreToLabel(score: number): string {
  if (score >= 80) return "Critical";
  if (score >= 60) return "High";
  if (score >= 40) return "Medium";
  if (score >= 20) return "Low";
  return "Backlog";
}

function scoreToColor(score: number): string {
  if (score >= 80) return "#dc2626";
  if (score >= 60) return "#f59e0b";
  if (score >= 40) return "#3b82f6";
  if (score >= 20) return "#6b7280";
  return "#9ca3af";
}

export const PriorityQueueView: React.FC<PriorityQueueViewProps> = ({ items, onExportTriage, onUpdateStatus }) => {
  const [sortBy, setSortBy] = React.useState<"priority" | "frequency" | "created">("priority");
  const [filterType, setFilterType] = React.useState<string>("");

  const sorted = [...items].sort((a, b) => {
    if (sortBy === "priority") return b.priorityScore - a.priorityScore;
    if (sortBy === "frequency") return b.frequency - a.frequency;
    return b.createdAt - a.createdAt;
  });

  const filtered = filterType ? sorted.filter((i) => i.type === filterType) : sorted;

  return (
    <div className="glass-panel" style={{ padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Priority Queue</h3>
        <button onClick={onExportTriage}
          style={{ padding: "4px 12px", fontSize: "0.75rem", borderRadius: 6, border: "1px solid #d1d5db", background: "#fff", cursor: "pointer" }}>
          Export to Triage
        </button>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as any)}
          style={{ padding: "4px 8px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "0.75rem" }}>
          <option value="priority">Sort by Priority</option>
          <option value="frequency">Sort by Frequency</option>
          <option value="created">Sort by Date</option>
        </select>
        {["", "bug", "feature", "feedback"].map((t) => (
          <button key={t}
            onClick={() => setFilterType(filterType === t ? "" : t)}
            style={{
              padding: "2px 10px", fontSize: "0.7rem", borderRadius: 12,
              border: `1px solid ${filterType === t ? "#3b82f6" : "#d1d5db"}`,
              background: filterType === t ? "#3b82f6" : "transparent",
              color: filterType === t ? "#fff" : "#374151", cursor: "pointer",
            }}>
            {t || "All"}
          </button>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 400, overflowY: "auto" }}>
        {filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: 24, color: "#9ca3af", fontSize: "0.85rem" }}>
            Queue is empty
          </div>
        ) : (
          filtered.map((item) => {
            const label = scoreToLabel(item.priorityScore);
            const color = scoreToColor(item.priorityScore);
            return (
              <div key={item.id}
                style={{
                  padding: "8px 12px", borderRadius: 6, border: "1px solid rgba(0,0,0,0.06)",
                  display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8,
                }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{
                      display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: color,
                    }} />
                    <span style={{ fontWeight: 600, fontSize: "0.8rem" }}>{item.title}</span>
                    <span style={{ fontSize: "0.65rem", color: "#6b7280" }}>({item.type})</span>
                  </div>
                  <div style={{ fontSize: "0.72rem", color: "#6b7280", marginTop: 2 }}>
                    <span>Impact: {item.impact} · Frequency: {item.frequency} · Score: {item.priorityScore}</span>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{
                    padding: "1px 8px", borderRadius: 8, fontSize: "0.65rem", fontWeight: 600,
                    background: color, color: "#fff",
                  }}>
                    {label}
                  </span>
                  <select value={item.status} onChange={(e) => onUpdateStatus(item.id, e.target.value)}
                    style={{ fontSize: "0.7rem", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: 4 }}>
                    <option value="new">new</option>
                    <option value="triaged">triaged</option>
                    <option value="in_progress">in progress</option>
                    <option value="resolved">resolved</option>
                  </select>
                </div>
              </div>
            );
          })
        )}
      </div>
      <div style={{ marginTop: 10, fontSize: "0.7rem", color: "#9ca3af", display: "flex", gap: 16 }}>
        <span>Scoring: Impact × Frequency = Priority</span>
        <span>{filtered.length} items</span>
      </div>
    </div>
  );
};
