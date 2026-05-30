import React from "react";
import { useRuntimeStore } from "../stores/runtime";
import { StatusBadge } from "../styles/design-system/status-badge";

export const Projects: React.FC = () => {
  const { projects, isConnected } = useRuntimeStore();

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          Projects
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Manage memory spaces, skill lanes, and agent teams per project
        </p>
      </div>

      <div className="glass-panel" style={{ padding: 16 }}>
        <div className="section-header">All Projects</div>
        {projects.length === 0 && (
          <p style={{ color: "#9ca3af", fontSize: "0.85rem", padding: 24, textAlign: "center" }}>
            {isConnected ? "No projects yet. Create your first project to get started." : "Connect to runtime to view projects."}
          </p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {projects.map((p) => (
            <div
              key={p.id}
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
                background: "rgba(59,130,246,0.1)", color: "#2563eb",
              }}>{p.name[0]}</div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{p.name}</span>
                  <StatusBadge state={p.status === "active" ? "active" : p.status === "archived" ? "down" : "degraded"} label={p.status} size="sm" />
                </div>
                <p style={{ margin: "2px 0 0", fontSize: "0.75rem", color: "#9ca3af" }}>
                  {p.agent_count} agents · {p.memory_space}
                </p>
              </div>
              <span style={{ fontSize: "0.75rem", color: "#9ca3af" }}>{p.created_at}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
