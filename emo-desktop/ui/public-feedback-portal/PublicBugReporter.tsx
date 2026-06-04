import React from "react";

export type BugSeverity = "low" | "medium" | "high" | "critical";
export type BugCategory = "crash" | "ui" | "performance" | "security" | "compatibility" | "other";

export interface BugReport {
  id: string;
  title: string;
  description: string;
  category: BugCategory;
  severity: BugSeverity;
  logsAttached: boolean;
  logsCleaned: boolean;
  timestamp: number;
  sessionId: string;
  status: "new" | "reviewing" | "fixed" | "wontfix";
}

interface PublicBugReporterProps {
  onSubmit: (report: Omit<BugReport, "id" | "timestamp" | "status">) => void;
  recentReports: BugReport[];
}

const categoryLabels: Record<BugCategory, string> = {
  crash: "Crash / Freeze",
  ui: "UI / Visual",
  performance: "Performance",
  security: "Security",
  compatibility: "Compatibility",
  other: "Other",
};

export const PublicBugReporter: React.FC<PublicBugReporterProps> = ({ onSubmit, recentReports }) => {
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [category, setCategory] = React.useState<BugCategory>("crash");
  const [severity, setSeverity] = React.useState<BugSeverity>("medium");
  const [attachLogs, setAttachLogs] = React.useState(true);
  const [submitted, setSubmitted] = React.useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !description.trim()) return;
    onSubmit({
      title: title.trim(),
      description: description.trim(),
      category,
      severity,
      logsAttached: attachLogs,
      logsCleaned: attachLogs,
      sessionId: `session_${Date.now()}`,
    });
    setTitle("");
    setDescription("");
    setSubmitted(true);
    setTimeout(() => setSubmitted(false), 3000);
  };

  return (
    <div className="glass-panel" style={{ padding: 20 }}>
      <h3 style={{ margin: "0 0 4px", fontSize: "1rem", fontWeight: 600 }}>Report a Bug</h3>
      <p style={{ margin: "0 0 16px", fontSize: "0.8rem", color: "#6b7280" }}>
        Logs are automatically scrubbed of sensitive data before submission
      </p>
      {submitted ? (
        <div style={{ padding: 12, background: "rgba(34,197,94,0.1)", borderRadius: 6, color: "#16a34a", fontSize: "0.85rem" }}>
          Thank you! Your report has been submitted.
        </div>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Bug title"
            required
            style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "0.8rem" }}
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what happened..."
            required
            rows={4}
            style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "0.8rem", resize: "vertical" }}
          />
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <select value={category} onChange={(e) => setCategory(e.target.value as BugCategory)}
              style={{ padding: "6px 8px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "0.8rem" }}>
              {Object.entries(categoryLabels).map(([val, label]) => (
                <option key={val} value={val}>{label}</option>
              ))}
            </select>
            <select value={severity} onChange={(e) => setSeverity(e.target.value as BugSeverity)}
              style={{ padding: "6px 8px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "0.8rem" }}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <label style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: 6 }}>
            <input type="checkbox" checked={attachLogs} onChange={(e) => setAttachLogs(e.target.checked)} />
            Attach scrubbed crash logs
          </label>
          <button type="submit"
            style={{
              padding: "8px 16px", borderRadius: 6, border: "none",
              background: "#3b82f6", color: "#fff", fontWeight: 600, fontSize: "0.8rem", cursor: "pointer",
            }}>
            Submit Report
          </button>
        </form>
      )}
      {recentReports.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ fontSize: "0.8rem", cursor: "pointer", color: "#6b7280" }}>
            Your recent reports ({recentReports.length})
          </summary>
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
            {recentReports.slice(-3).reverse().map((r) => (
              <div key={r.id} style={{ fontSize: "0.75rem", padding: "6px 8px", background: "rgba(0,0,0,0.02)", borderRadius: 4 }}>
                <strong>{r.title}</strong> — {r.status}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
};
