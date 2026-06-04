import React from "react";

export interface PortalCompany {
  id: string;
  name: string;
  status: "active" | "suspended" | "expired";
  licenseKey: string;
  expiresAt: number;
  maxAgents: number;
  lastActivity: number | null;
  createdAt: number;
}

interface CompanyRegistryProps {
  companies: PortalCompany[];
  onToggleStatus: (id: string, newStatus: "active" | "suspended") => void;
  onRegister: () => void;
}

const statusColors: Record<string, string> = {
  active: "#22c55e",
  suspended: "#f59e0b",
  expired: "#ef4444",
};

export const CompanyRegistry: React.FC<CompanyRegistryProps> = ({ companies, onToggleStatus, onRegister }) => {
  return (
    <div className="glass-panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(0,0,0,0.06)", fontWeight: 600, fontSize: "0.85rem", display: "flex", alignItems: "center", gap: 8 }}>
        <span>Company Registry</span>
        <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "#9ca3af" }}>{companies.length} companies</span>
        <button onClick={onRegister} style={addButtonStyle}>+ Register</button>
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {companies.length === 0 && (
          <p style={{ padding: "24px 8px", textAlign: "center", color: "#9ca3af", fontSize: "0.8rem" }}>No companies registered</p>
        )}
        {companies.map((c) => (
          <div key={c.id} style={cardStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: statusColors[c.status], flexShrink: 0 }} />
              <span style={{ fontWeight: 600, fontSize: "0.8rem" }}>{c.name}</span>
              <span style={{ fontSize: "0.7rem", color: "#9ca3af", marginLeft: "auto" }}>
                {new Date(c.expiresAt).toLocaleDateString()}
              </span>
            </div>
            <div style={{ display: "flex", gap: 12, fontSize: "0.7rem", color: "#6b7280", marginLeft: 16 }}>
              <span>ID: {c.id.slice(0, 8)}</span>
              <span>Agents: {c.maxAgents}</span>
              <span>Key: {c.licenseKey.slice(0, 8)}...</span>
            </div>
            <div style={{ display: "flex", gap: 6, marginTop: 6, marginLeft: 16 }}>
              {c.status === "active" ? (
                <button onClick={() => onToggleStatus(c.id, "suspended")} style={{ ...smallBtnStyle, color: "#f59e0b", borderColor: "#f59e0b" }}>
                  Suspend
                </button>
              ) : c.status === "suspended" ? (
                <button onClick={() => onToggleStatus(c.id, "active")} style={{ ...smallBtnStyle, color: "#22c55e", borderColor: "#22c55e" }}>
                  Reactivate
                </button>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const cardStyle: React.CSSProperties = {
  padding: "10px 12px", marginBottom: 6, borderRadius: 8,
  border: "1px solid rgba(0,0,0,0.06)", background: "white",
};

const smallBtnStyle: React.CSSProperties = {
  padding: "4px 10px", fontSize: "0.7rem", border: "1px solid rgba(0,0,0,0.1)",
  borderRadius: 4, background: "#f3f4f6", cursor: "pointer", fontWeight: 500,
};

const addButtonStyle: React.CSSProperties = {
  padding: "4px 10px", fontSize: "0.7rem", border: "1px solid #3b82f6",
  borderRadius: 4, background: "#3b82f6", color: "white", cursor: "pointer", fontWeight: 500,
};
