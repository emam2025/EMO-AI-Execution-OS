import React from "react";

export type NodeState = "pending" | "running" | "completed" | "failed" | "skipped";

export interface TimelineNodeProps {
  label: string;
  state: NodeState;
  description?: string;
  durationMs?: number;
  depth?: number;
  isLast?: boolean;
  onClick?: () => void;
}

const stateColors: Record<NodeState, { dot: string; bg: string; border: string }> = {
  pending: { dot: "#d1d5db", bg: "rgba(209,213,219,0.08)", border: "rgba(209,213,219,0.2)" },
  running: { dot: "#3b82f6", bg: "rgba(59,130,246,0.08)", border: "rgba(59,130,246,0.3)" },
  completed: { dot: "#22c55e", bg: "rgba(34,197,94,0.08)", border: "rgba(34,197,94,0.2)" },
  failed: { dot: "#ef4444", bg: "rgba(239,68,68,0.08)", border: "rgba(239,68,68,0.2)" },
  skipped: { dot: "#9ca3af", bg: "rgba(156,163,175,0.05)", border: "rgba(156,163,175,0.15)" },
};

const stateLabel: Record<NodeState, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  skipped: "Skipped",
};

export const TimelineNode: React.FC<TimelineNodeProps> = ({
  label,
  state,
  description,
  durationMs,
  depth = 0,
  isLast = false,
  onClick,
}) => {
  const colors = stateColors[state];
  const isRunning = state === "running";

  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      className="timeline-node"
      style={{
        display: "flex",
        gap: 12,
        padding: "10px 14px",
        marginLeft: depth * 20,
        borderRadius: 8,
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        cursor: onClick ? "pointer" : "default",
        transition: "all 0.2s ease-out",
        animation: "smooth-fade-in 0.2s ease-out",
      }}
    >
      {/* Vertical line + dot */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 16 }}>
        <div
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: colors.dot,
            marginTop: 4,
            boxShadow: isRunning ? `0 0 0 4px ${colors.border}` : undefined,
            animation: isRunning ? "pulse-dot 2s ease-in-out infinite" : undefined,
          }}
        />
        {!isLast && (
          <div style={{ width: 1, flex: 1, background: "rgba(0,0,0,0.06)", marginTop: 4 }} />
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{label}</span>
          <span
            className={`status-badge status-badge-${state === "running" ? "active" : state === "failed" ? "down" : state}`}
            style={{ fontSize: "0.65rem", padding: "1px 6px" }}
          >
            {stateLabel[state]}
          </span>
          {durationMs !== undefined && (
            <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "#9ca3af" }}>
              {durationMs >= 1000
                ? `${(durationMs / 1000).toFixed(1)}s`
                : `${durationMs}ms`}
            </span>
          )}
        </div>
        {description && (
          <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280", lineHeight: 1.4 }}>
            {description}
          </p>
        )}
      </div>
    </div>
  );
};

/**
 * Timeline container — wraps TimelineNode children.
 */
export const ExecutionTimeline: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({
  children,
  style,
}) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: 6,
      padding: 12,
      ...style,
    }}
  >
    {children}
  </div>
);
