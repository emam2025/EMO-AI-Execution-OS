import React from "react";
import { useMemoryStore } from "../store/memoryStore";

const AuditLogViewer: React.FC = () => {
  const auditLog = useMemoryStore((s) => s.auditLog);

  return (
    <div>
      <div style={{ marginBottom: 16, display: "flex", gap: 12, alignItems: "center" }}>
        <div style={{ fontSize: "0.75rem", color: "#71717a", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Chain Integrity
        </div>
        <span style={{
          padding: "4px 10px", borderRadius: 12,
          background: auditLog.length === 0 || auditLog.every((e) => e.chainVerified)
            ? "rgba(52,211,153,0.15)" : "rgba(248,113,113,0.15)",
          color: auditLog.length === 0 || auditLog.every((e) => e.chainVerified) ? "#34d399" : "#f87171",
          fontSize: "0.75rem", fontWeight: 600,
        }}>
          {auditLog.length === 0 || auditLog.every((e) => e.chainVerified) ? "VERIFIED" : "TAMPERED"}
        </span>
        <span style={{ fontSize: "0.75rem", color: "#52525b", flex: 1, textAlign: "right" }}>
          {auditLog.length} entries
        </span>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
        <thead>
          <tr style={{ color: "#71717a", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <th style={{ textAlign: "left", padding: "8px 10px" }}>Timestamp</th>
            <th style={{ textAlign: "left", padding: "8px 10px" }}>Action</th>
            <th style={{ textAlign: "left", padding: "8px 10px" }}>Target</th>
            <th style={{ textAlign: "left", padding: "8px 10px" }}>ID</th>
            <th style={{ textAlign: "left", padding: "8px 10px" }}>Reason</th>
            <th style={{ textAlign: "center", padding: "8px 10px" }}>Hash</th>
          </tr>
        </thead>
        <tbody>
          {auditLog.length === 0 ? (
            <tr><td colSpan={6} style={{ padding: 32, textAlign: "center", color: "#52525b" }}>
              No audit entries yet. Governance actions will appear here.
            </td></tr>
          ) : auditLog.map((e) => (
            <tr key={e.entryId} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
              <td style={{ padding: "8px 10px", fontFamily: "monospace", fontSize: "0.75rem", color: "#71717a" }}>
                {e.timestamp}
              </td>
              <td style={{ padding: "8px 10px" }}>
                <span style={{
                  padding: "2px 8px", borderRadius: 4, fontSize: "0.75rem",
                  background: e.action === "DELETE" ? "rgba(248,113,113,0.15)" :
                    e.action === "ARCHIVE" ? "rgba(250,204,21,0.15)" : "rgba(52,211,153,0.15)",
                  color: e.action === "DELETE" ? "#f87171" :
                    e.action === "ARCHIVE" ? "#fbbf24" : "#34d399",
                  fontWeight: 600,
                }}>
                  {e.action}
                </span>
              </td>
              <td style={{ padding: "8px 10px", color: "#a1a1aa" }}>{e.targetType}</td>
              <td style={{ padding: "8px 10px", fontFamily: "monospace", fontSize: "0.8rem" }}>{e.targetId}</td>
              <td style={{ padding: "8px 10px", color: "#71717a" }}>{e.reason}</td>
              <td style={{ padding: "8px 10px", textAlign: "center" }}>
                <span style={{
                  fontSize: "0.65rem", fontFamily: "monospace",
                  color: e.chainVerified ? "#34d399" : "#f87171",
                }}>
                  {e.sha256Hash.slice(0, 12)}…
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default AuditLogViewer;
