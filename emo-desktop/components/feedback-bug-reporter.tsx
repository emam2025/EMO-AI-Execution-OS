import React, { useState } from "react";

interface FeedbackPayload {
  environment: { os: string; version: string; runtime: string; memoryUsage: string };
  category: string;
  description: string;
  logs: string[];
  trace: string;
  timestamp: number;
}

const SENSITIVE_PATTERNS = [
  /sk-[a-zA-Z0-9]{20,}/g,
  /AIza[0-9A-Za-z_-]{35,}/g,
  /ghp_[a-zA-Z0-9]{36,}/g,
  /Bearer\s+[a-zA-Z0-9_-]{20,}/gi,
  /(?:password|secret|api[_-]?key)\s*[:=]\s*['"][^'"]+['"]/gi,
  /[\w.-]+@[\w.-]+\.\w{2,}/g,
];

function scrubText(text: string): string {
  let scrubbed = text;
  for (const pattern of SENSITIVE_PATTERNS) {
    scrubbed = scrubbed.replace(pattern, "[REDACTED]");
  }
  return scrubbed;
}

function collectEnvironmentInfo(): FeedbackPayload["environment"] {
  return {
    os: typeof navigator !== "undefined" ? navigator.platform : "unknown",
    version: typeof document !== "undefined" ? document.title : "0.1.0",
    runtime: "node",
    memoryUsage: typeof performance !== "undefined" && "memory" in performance
      ? `${(performance as any).memory?.usedJSHeapSize || 0} bytes`
      : "unknown",
  };
}

interface FeedbackBugReporterProps {
  onClose: () => void;
  onSubmit: (payload: FeedbackPayload) => Promise<{ success: boolean; id?: string }>;
}

export const FeedbackBugReporter: React.FC<FeedbackBugReporterProps> = ({ onClose, onSubmit }) => {
  const [category, setCategory] = useState("bug");
  const [description, setDescription] = useState("");
  const [logs, setLogs] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!description.trim()) {
      setError("Please describe the issue");
      return;
    }

    setSubmitting(true);
    setError("");

    const payload: FeedbackPayload = {
      environment: collectEnvironmentInfo(),
      category,
      description: scrubText(description),
      logs: logs.split("\n").filter((l) => l.trim()).map(scrubText),
      trace: scrubText(""),
      timestamp: Date.now(),
    };

    try {
      const result = await onSubmit(payload);
      if (result.success) {
        setSubmitted(true);
      } else {
        setError("Failed to submit report");
      }
    } catch {
      setError("Network error — please try again");
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div style={{
        position: "fixed", bottom: 24, right: 24, zIndex: 9999,
        padding: 20, borderRadius: 12, background: "white",
        boxShadow: "0 4px 24px rgba(0,0,0,0.15)", maxWidth: 360,
      }}>
        <div style={{ fontSize: "1.2rem", marginBottom: 8 }}>✅</div>
        <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: 4 }}>Report Submitted</div>
        <p style={{ fontSize: "0.75rem", color: "#6b7280", margin: 0 }}>
          Thank you! Your report has been received. The team will review it shortly.
        </p>
        <button onClick={onClose} style={dismissBtn}>Close</button>
      </div>
    );
  }

  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, zIndex: 9999,
      padding: 20, borderRadius: 12, background: "white",
      boxShadow: "0 4px 24px rgba(0,0,0,0.15)", width: 360,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: "1.1rem" }}>🐛</span>
        <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>Report an Issue</span>
        <button onClick={onClose} style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: "1rem" }}>✕</button>
      </div>

      <div style={{ marginBottom: 10 }}>
        <label style={{ fontSize: "0.7rem", color: "#6b7280", display: "block", marginBottom: 4 }}>Category</label>
        <select value={category} onChange={(e) => setCategory(e.target.value)} style={inputStyle}>
          <option value="bug">Bug</option>
          <option value="performance">Performance</option>
          <option value="feature">Feature Request</option>
          <option value="security">Security Concern</option>
          <option value="other">Other</option>
        </select>
      </div>

      <div style={{ marginBottom: 10 }}>
        <label style={{ fontSize: "0.7rem", color: "#6b7280", display: "block", marginBottom: 4 }}>Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe the issue…"
          rows={3}
          style={{ ...inputStyle, resize: "vertical" }}
        />
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: "0.7rem", color: "#6b7280", display: "block", marginBottom: 4 }}>Recent Logs (optional)</label>
        <textarea
          value={logs}
          onChange={(e) => setLogs(e.target.value)}
          placeholder="Paste relevant log output…"
          rows={2}
          style={{ ...inputStyle, resize: "vertical", fontFamily: "monospace", fontSize: "0.65rem" }}
        />
        <p style={{ fontSize: "0.6rem", color: "#9ca3af", margin: "2px 0 0" }}>Sensitive data (keys, emails, passwords) will be automatically redacted.</p>
      </div>

      {error && <p style={{ fontSize: "0.7rem", color: "#ef4444", marginBottom: 8 }}>{error}</p>}

      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={handleSubmit} disabled={submitting} style={{
          flex: 1, padding: "8px 16px", border: "none", borderRadius: 6,
          background: submitting ? "#9ca3af" : "#3b82f6", color: "white",
          fontWeight: 600, fontSize: "0.75rem", cursor: submitting ? "not-allowed" : "pointer",
        }}>
          {submitting ? "Submitting…" : "Send Report"}
        </button>
      </div>
    </div>
  );
};

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "6px 10px", fontSize: "0.75rem",
  border: "1px solid rgba(0,0,0,0.1)", borderRadius: 6,
  background: "#f9fafb", outline: "none", boxSizing: "border-box",
};

const dismissBtn: React.CSSProperties = {
  marginTop: 10, padding: "6px 14px", border: "none", borderRadius: 6,
  background: "#f3f4f6", color: "#374151", fontSize: "0.7rem",
  fontWeight: 500, cursor: "pointer", width: "100%",
};
