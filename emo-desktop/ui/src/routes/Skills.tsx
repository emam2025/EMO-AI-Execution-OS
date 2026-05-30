import React from "react";
import { useRuntimeStore } from "../stores/runtime";
import { StatusBadge } from "../styles/design-system/status-badge";

const tierColor: Record<string, "active" | "degraded" | "down"> = {
  extracted: "degraded",
  validated: "active",
  production: "active",
  deprecated: "down",
};

export const Skills: React.FC = () => {
  const { skills, isConnected } = useRuntimeStore();

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          Skills
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Extracted skills, rankings, and evolution history
        </p>
      </div>

      <div className="glass-panel" style={{ padding: 16 }}>
        <div className="section-header">Skill Library</div>
        {skills.length === 0 && (
          <p style={{ color: "#9ca3af", fontSize: "0.85rem", padding: 24, textAlign: "center" }}>
            {isConnected ? "No skills extracted yet. Skills are auto-extracted from execution traces." : "Connect to runtime to view skills."}
          </p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {skills.map((skill) => (
            <div
              key={skill.id}
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
                background: "rgba(139,92,246,0.1)", color: "#7c3aed",
              }}>{skill.name[0]}</div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{skill.name}</span>
                  <StatusBadge state={tierColor[skill.tier] ?? "degraded"} label={skill.tier} size="sm" />
                </div>
                <p style={{ margin: "2px 0 0", fontSize: "0.75rem", color: "#9ca3af" }}>
                  {(skill.accuracy * 100).toFixed(0)}% accuracy · {skill.usage_count} uses · {skill.source}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
