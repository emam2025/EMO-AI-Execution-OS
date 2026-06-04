import React from "react";

interface ErrorRecoveryProps {
  message?: string;
  onRetry?: () => void;
}

export const ErrorRecovery: React.FC<ErrorRecoveryProps> = ({ message = "Something went wrong.", onRetry }) => (
  <div className="glass-panel" style={{
    padding: 24, display: "flex", flexDirection: "column", alignItems: "center",
    gap: 8, textAlign: "center", border: "1px solid rgba(239,68,68,0.2)",
  }}>
    <span style={{ fontSize: "1.5rem" }}>⚠️</span>
    <p style={{ margin: 0, fontSize: "0.85rem", color: "#dc2626" }}>{message}</p>
    {onRetry && (
      <button onClick={onRetry} style={{
        marginTop: 4, padding: "6px 16px", borderRadius: 6, border: "1px solid rgba(239,68,68,0.3)",
        background: "transparent", color: "#dc2626", fontWeight: 500, fontSize: "0.8rem",
        cursor: "pointer",
      }}>Retry</button>
    )}
  </div>
);
