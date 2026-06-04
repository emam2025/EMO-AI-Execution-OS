import React from "react";

export interface FeatureRequest {
  id: string;
  title: string;
  description: string;
  votes: number;
  userVoted: boolean;
  status: "under_review" | "planned" | "in_progress" | "completed" | "declined";
  createdAt: number;
  category: string;
}

interface FeatureRequestBoardProps {
  requests: FeatureRequest[];
  onVote: (requestId: string) => void;
  onSubmitRequest: (title: string, description: string, category: string) => void;
}

const statusColors: Record<string, string> = {
  under_review: "#f59e0b",
  planned: "#3b82f6",
  in_progress: "#8b5cf6",
  completed: "#22c55e",
  declined: "#6b7280",
};

const statusLabels: Record<string, string> = {
  under_review: "Under Review",
  planned: "Planned",
  in_progress: "In Progress",
  completed: "Completed",
  declined: "Declined",
};

export const FeatureRequestBoard: React.FC<FeatureRequestBoardProps> = ({ requests, onVote, onSubmitRequest }) => {
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [category, setCategory] = React.useState("feature");
  const [showForm, setShowForm] = React.useState(false);

  const sorted = [...requests].sort((a, b) => b.votes - a.votes);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !description.trim()) return;
    onSubmitRequest(title.trim(), description.trim(), category);
    setTitle("");
    setDescription("");
    setShowForm(false);
  };

  return (
    <div className="glass-panel" style={{ padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Feature Requests</h3>
        <button onClick={() => setShowForm(!showForm)}
          style={{
            padding: "4px 12px", fontSize: "0.75rem", borderRadius: 6,
            border: "1px solid #3b82f6", background: showForm ? "#3b82f6" : "transparent",
            color: showForm ? "#fff" : "#3b82f6", cursor: "pointer",
          }}>
          {showForm ? "Cancel" : "New Request"}
        </button>
      </div>
      {showForm && (
        <form onSubmit={handleSubmit} style={{ marginBottom: 16, display: "flex", flexDirection: "column", gap: 8 }}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Feature title" required
            style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "0.8rem" }} />
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Describe the feature..." required rows={3}
            style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "0.8rem", resize: "vertical" }} />
          <select value={category} onChange={(e) => setCategory(e.target.value)}
            style={{ padding: "6px 8px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "0.8rem" }}>
            <option value="feature">New Feature</option>
            <option value="improvement">Improvement</option>
            <option value="integration">Integration</option>
            <option value="api">API</option>
            <option value="docs">Documentation</option>
          </select>
          <button type="submit"
            style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: "#3b82f6", color: "#fff", fontWeight: 600, fontSize: "0.8rem", cursor: "pointer" }}>
            Submit Request
          </button>
        </form>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 400, overflowY: "auto" }}>
        {sorted.length === 0 ? (
          <div style={{ textAlign: "center", padding: 24, color: "#9ca3af", fontSize: "0.85rem" }}>
            No feature requests yet
          </div>
        ) : (
          sorted.map((req) => (
            <div key={req.id}
              style={{
                padding: "10px 12px", borderRadius: 8, border: "1px solid rgba(0,0,0,0.06)",
                display: "flex", gap: 12, alignItems: "flex-start",
              }}>
              <button onClick={() => onVote(req.id)}
                style={{
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
                  padding: "4px 8px", borderRadius: 6, border: `1px solid ${req.userVoted ? "#3b82f6" : "#d1d5db"}`,
                  background: req.userVoted ? "rgba(59,130,246,0.1)" : "transparent",
                  cursor: "pointer", minWidth: 40,
                }}>
                <span style={{ fontSize: "0.9rem", color: req.userVoted ? "#3b82f6" : "#6b7280" }}>▲</span>
                <span style={{ fontSize: "0.85rem", fontWeight: 700, color: req.userVoted ? "#3b82f6" : "#374151" }}>{req.votes}</span>
              </button>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>{req.title}</span>
                  <span style={{
                    display: "inline-block", padding: "1px 6px", borderRadius: 8, fontSize: "0.65rem", fontWeight: 600,
                    background: statusColors[req.status] || "#6b7280", color: "#fff",
                  }}>
                    {statusLabels[req.status]}
                  </span>
                </div>
                <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: 2 }}>{req.description}</div>
                <div style={{ fontSize: "0.7rem", color: "#9ca3af", marginTop: 2 }}>{req.category}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
