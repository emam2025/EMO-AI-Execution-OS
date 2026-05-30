import React, { useRef, useEffect } from "react";
import { useRuntimeStore } from "../../stores/runtime";
import type { RuntimeEvent } from "../../types/telemetry";

const eventColors: Record<string, string> = {
  task_started: "#3b82f6",
  node_completed: "#22c55e",
  agent_warning: "#f59e0b",
  runtime_error: "#ef4444",
  trace_indexed: "#8b5cf6",
  gateway_request: "#06b6d4",
  gateway_failover: "#f97316",
  gateway_health: "#6b7280",
};

export const ActivityStream: React.FC = () => {
  const { events, isConnected } = useRuntimeStore();
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [events.length]);

  return (
    <div className="glass-panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(0,0,0,0.06)", display: "flex", alignItems: "center", gap: 8 }}>
        <span className={isConnected ? "live-dot" : "live-dot-disconnected"} />
        <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>
          Activity Stream {isConnected ? "• Live" : "• Disconnected"}
        </span>
        <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "#9ca3af" }}>
          {events.length} events
        </span>
      </div>
      <div ref={listRef} style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {events.length === 0 && (
          <p style={{ padding: "24px 8px", textAlign: "center", color: "#9ca3af", fontSize: "0.8rem" }}>
            {isConnected ? "Waiting for events…" : "Connect to runtime to see live activity."}
          </p>
        )}
        {events.map((event, i) => (
          <ActivityEvent key={i} event={event} />
        ))}
      </div>
    </div>
  );
};

const ActivityEvent: React.FC<{ event: RuntimeEvent }> = ({ event }) => {
  const dotColor = eventColors[event.type] ?? "#6b7280";
  const time = event.timestamp
    ? new Date(event.timestamp).toLocaleTimeString()
    : "--";

  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        padding: "6px 8px",
        borderRadius: 6,
        fontSize: "0.8rem",
        transition: "all 0.12s ease-out",
        animation: "smooth-fade-in 0.15s ease-out",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 12, paddingTop: 4 }}>
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: dotColor }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ fontWeight: 500, color: dotColor }}>{event.type}</span>
          {event.trace_id && (
            <span style={{ color: "#9ca3af", fontSize: "0.7rem", fontFamily: "monospace" }}>
              {event.trace_id.slice(0, 12)}…
            </span>
          )}
          <span style={{ marginLeft: "auto", color: "#9ca3af", fontSize: "0.7rem" }}>{time}</span>
        </div>
        {event.type === "gateway_request" && event.payload?.provider_id && (
          <p style={{ margin: 0, color: "#6b7280", fontSize: "0.75rem" }}>
            → {String(event.payload.provider_id)}
          </p>
        )}
        {event.type === "gateway_failover" && event.payload?.trigger && (
          <p style={{ margin: 0, color: "#f97316", fontSize: "0.75rem" }}>
            ⚡ {String(event.payload.trigger)} → {String(event.payload.fallback_provider ?? "none")}
          </p>
        )}
      </div>
    </div>
  );
};
