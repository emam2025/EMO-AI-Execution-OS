import React from "react";
import { useMemoryStore } from "../store/memoryStore";

const ProjectMemoryBrowser: React.FC = () => {
  const spaces = useMemoryStore((s) => s.spaces);
  const [selected, setSelected] = React.useState("");
  const projects = spaces.filter((s) => s.type === "project");

  return (
    <div style={{ display: "flex", gap: 24 }}>
      <div style={{ width: 260, flexShrink: 0 }}>
        <div style={{ fontSize: "0.75rem", color: "#71717a", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>
          Projects
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {projects.length === 0 && (
            <div style={{ color: "#52525b", fontSize: "0.85rem", padding: 8 }}>No projects yet.</div>
          )}
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => setSelected(p.id)}
              style={{
                textAlign: "left", padding: "10px 12px", borderRadius: 8, border: "none",
                background: selected === p.id ? "rgba(139,92,246,0.15)" : "transparent",
                color: selected === p.id ? "#a78bfa" : "#e4e4e7",
                fontWeight: selected === p.id ? 600 : 400,
                fontSize: "0.85rem", cursor: "pointer",
              }}
            >
              📁 {p.name}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 24, padding: 16, borderRadius: 8, background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)" }}>
          <div style={{ fontSize: "0.75rem", color: "#52525b", textTransform: "uppercase" }}>Filters</div>
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
            {["episodic", "semantic", "procedural"].map((l) => (
              <label key={l} style={{ fontSize: "0.85rem", color: "#a1a1aa", display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" defaultChecked style={{ accentColor: "#a78bfa" }} /> {l}
              </label>
            ))}
          </div>
        </div>
      </div>
      <div style={{ flex: 1, padding: 24, borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)" }}>
        {!selected ? (
          <div style={{ textAlign: "center", color: "#52525b", padding: 48 }}>
            Select a project from the left panel
          </div>
        ) : (
          <div style={{ color: "#71717a", fontSize: "0.85rem" }}>
            Project <strong style={{ color: "#e4e4e7" }}>{selected}</strong> memory entries will be listed here when connected to the backend API.
          </div>
        )}
      </div>
    </div>
  );
};

export default ProjectMemoryBrowser;
