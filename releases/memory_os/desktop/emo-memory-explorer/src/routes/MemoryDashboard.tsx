import React from "react";
import { useMemoryStore, type SpaceInfo } from "../store/memoryStore";

const GlassPanel: React.FC<{ title: string; value: string | number; subtitle?: string }> = ({
  title, value, subtitle,
}) => (
  <div style={{
    flex: 1, minWidth: 160, padding: 20, borderRadius: 12,
    background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)",
    backdropFilter: "blur(12px)",
  }}>
    <div style={{ fontSize: "0.75rem", color: "#71717a", textTransform: "uppercase", letterSpacing: "0.05em" }}>{title}</div>
    <div style={{ fontSize: "1.8rem", fontWeight: 700, color: "#a78bfa", marginTop: 8 }}>{value}</div>
    {subtitle && <div style={{ fontSize: "0.75rem", color: "#52525b", marginTop: 4 }}>{subtitle}</div>}
  </div>
);

const MemoryDashboard: React.FC = () => {
  const stats = useMemoryStore((s) => s.stats);
  const spaces = useMemoryStore((s) => s.spaces);
  return (
    <div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
        <GlassPanel title="Total Entries" value={stats.totalEntries} />
        <GlassPanel title="Graph Nodes" value={stats.totalGraphNodes} />
        <GlassPanel title="Graph Edges" value={stats.totalEdges} />
        <GlassPanel title="Active Projects" value={stats.projectsCount} />
        <GlassPanel title="Active Agents" value={stats.agentsActive} subtitle={`Last optimized: ${stats.lastOptimized}`} />
      </div>
      <h3 style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: 12, color: "#e4e4e7" }}>Memory Spaces</h3>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
        <thead>
          <tr style={{ color: "#71717a", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <th style={{ textAlign: "left", padding: "8px 12px" }}>Type</th>
            <th style={{ textAlign: "left", padding: "8px 12px" }}>Name</th>
            <th style={{ textAlign: "right", padding: "8px 12px" }}>Entries</th>
            <th style={{ textAlign: "right", padding: "8px 12px" }}>Last Activity</th>
          </tr>
        </thead>
        <tbody>
          {spaces.length === 0 ? (
            <tr><td colSpan={4} style={{ padding: 24, textAlign: "center", color: "#52525b" }}>No spaces yet. Store some memory to get started.</td></tr>
          ) : spaces.map((s) => (
            <tr key={s.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
              <td style={{ padding: "8px 12px" }}><span style={{ color: s.type === "project" ? "#a78bfa" : "#34d399" }}>{s.type === "project" ? "📁" : "🤖"} {s.type}</span></td>
              <td style={{ padding: "8px 12px" }}>{s.name}</td>
              <td style={{ padding: "8px 12px", textAlign: "right" }}>{s.entryCount}</td>
              <td style={{ padding: "8px 12px", textAlign: "right", color: "#71717a" }}>{s.lastActivity}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default MemoryDashboard;
