import React from "react";

interface EmptyStateProps {
  icon?: string;
  title: string;
  description: string;
  action?: { label: string; onClick: () => void };
}

export const EmptyState: React.FC<EmptyStateProps> = ({ icon = "📭", title, description, action }) => (
  <div style={{
    display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
    padding: 48, gap: 8, textAlign: "center", flex: 1,
  }}>
    <span style={{ fontSize: "2rem" }}>{icon}</span>
    <h3 style={{ margin: 0, fontWeight: 600, fontSize: "0.95rem", color: "#374151" }}>{title}</h3>
    <p style={{ margin: 0, fontSize: "0.8rem", color: "#9ca3af", maxWidth: 360 }}>{description}</p>
    {action && (
      <button onClick={action.onClick} style={{
        marginTop: 8, padding: "8px 18px", borderRadius: 8, border: "none",
        background: "#3b82f6", color: "#fff", fontWeight: 500, fontSize: "0.8rem",
        cursor: "pointer", transition: "all 0.12s",
      }}>{action.label}</button>
    )}
  </div>
);
