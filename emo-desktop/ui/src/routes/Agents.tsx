import React from "react";
import { useRuntimeStore } from "../stores/runtime";
import { StatusBadge } from "../styles/design-system/status-badge";

export const Agents: React.FC = () => {
  const { health, isConnected } = useRuntimeStore();

  const agents = [
    { name: "Planner", status: health?.planner ?? false, desc: "Task classification & decomposition", capabilities: ["DAG synthesis", "Goal decomposition", "Feasibility analysis"] },
    { name: "Critic", status: health?.critic ?? false, desc: "Plan evaluation & scope verification", capabilities: ["Integrity checks", "Scope validation", "Risk assessment"] },
    { name: "Optimizer", status: health?.optimizer ?? false, desc: "Cost & performance optimization", capabilities: ["Cost minimization", "Resource tuning", "Throughput optimization"] },
  ];

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          Agents
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Agent health, capabilities, and runtime status
        </p>
      </div>

      <div className="glass-panel" style={{ padding: 16 }}>
        <div className="section-header">Available Agents</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {agents.map((agent) => (
            <div
              key={agent.name}
              className="smooth-enter"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "14px 16px",
                borderRadius: 8,
                background: "rgba(255,255,255,0.5)",
                border: "1px solid rgba(0,0,0,0.04)",
              }}
            >
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 700, fontSize: "0.9rem",
                background: agent.status ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
                color: agent.status ? "#16a34a" : "#dc2626",
              }}>
                {agent.name[0]}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{agent.name}</span>
                  <StatusBadge state={agent.status ? "active" : "down"} label={agent.status ? "Online" : "Offline"} size="sm" />
                </div>
                <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>{agent.desc}</p>
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  {agent.capabilities.map((c) => (
                    <span key={c} style={{
                      fontSize: "0.65rem", padding: "2px 8px", borderRadius: 4,
                      background: "rgba(59,130,246,0.08)", color: "#2563eb",
                    }}>{c}</span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="glass-panel" style={{ padding: 16, display: "flex", alignItems: "center", gap: 16 }}>
        <div>
          <div className="section-header" style={{ marginBottom: 4 }}>Runtime Status</div>
          <StatusBadge state={isConnected ? "active" : "down"} label={isConnected ? "Connected" : "Disconnected"} />
        </div>
        <div>
          <div className="section-header" style={{ marginBottom: 4 }}>State Machine</div>
          <StatusBadge state={health?.state_machine ? "active" : "down"} label={health?.state_machine ? "Operational" : "Offline"} />
        </div>
      </div>
    </div>
  );
};
