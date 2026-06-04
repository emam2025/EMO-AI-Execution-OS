import React from "react";

interface LoadingSkeletonProps {
  lines?: number;
  variant?: "card" | "list" | "text";
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({ lines = 3, variant = "text" }) => {
  const style: React.CSSProperties = {
    borderRadius: 6, background: "rgba(0,0,0,0.06)",
    animation: "skeleton-pulse 1.5s ease-in-out infinite",
  };

  if (variant === "card") {
    return (
      <div className="glass-panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ ...style, height: 16, width: "60%" }} />
        <div style={{ ...style, height: 12, width: "80%" }} />
        <div style={{ ...style, height: 12, width: "40%" }} />
      </div>
    );
  }

  if (variant === "list") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="glass-panel" style={{
            padding: 14, display: "flex", alignItems: "center", gap: 12,
          }}>
            <div style={{ ...style, width: 32, height: 32, borderRadius: 8 }} />
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ ...style, height: 12, width: "50%" }} />
              <div style={{ ...style, height: 10, width: "30%" }} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} style={{ ...style, height: 10, width: `${70 - i * 15}%` }} />
      ))}
    </div>
  );
};
