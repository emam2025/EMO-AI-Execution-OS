import React from "react";

export type BadgeState = "active" | "degraded" | "down" | "rate_limited" | "pending" | "running" | "completed" | "failed" | "skipped";

interface StatusBadgeProps {
  state: BadgeState;
  label?: string;
  size?: "sm" | "md";
}

const stateLabels: Record<BadgeState, string> = {
  active: "Active",
  degraded: "Degraded",
  down: "Down",
  rate_limited: "Rate Limited",
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  skipped: "Skipped",
};

const stateToCssClass: Record<BadgeState, string> = {
  active: "status-badge-active",
  degraded: "status-badge-degraded",
  down: "status-badge-down",
  rate_limited: "status-badge-rate_limited",
  pending: "status-badge-down",
  running: "status-badge-active",
  completed: "status-badge-active",
  failed: "status-badge-down",
  skipped: "status-badge-degraded",
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ state, label, size = "md" }) => (
  <span
    className={`status-badge ${stateToCssClass[state]}`}
    style={size === "sm" ? { fontSize: "0.65rem", padding: "1px 6px" } : undefined}
  >
    {label ?? stateLabels[state]}
  </span>
);
