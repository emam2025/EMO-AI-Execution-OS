import React from "react";

const SESSION_DATA = [
  { session: "ct-20260501", agent: "agent-alpha", decisions: 3, errors: 0, tokens: 1250 },
  { session: "ct-20260501", agent: "agent-beta", decisions: 1, errors: 2, tokens: 890 },
  { session: "ct-20260502", agent: "agent-alpha", decisions: 5, errors: 1, tokens: 2100 },
];

const AgentTraceViewer: React.FC = () => {
  const [agentFilter, setAgentFilter] = React.useState("");

  const filtered = agentFilter
    ? SESSION_DATA.filter((s) => s.agent === agentFilter)
    : SESSION_DATA;

  const agents = [...new Set(SESSION_DATA.map((s) => s.agent))];

  return (
    <div>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20 }}>
        <div style={{ fontSize: "0.75rem", color: "#71717a", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Agent Filter
        </div>
        <select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          style={{
            padding: "6px 12px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.1)",
            background: "rgba(255,255,255,0.05)", color: "#e4e4e7", fontSize: "0.85rem",
          }}
        >
          <option value="">All Agents</option>
          {agents.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
        <thead>
          <tr style={{ color: "#71717a", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <th style={{ textAlign: "left", padding: "10px 12px" }}>Session</th>
            <th style={{ textAlign: "left", padding: "10px 12px" }}>Agent</th>
            <th style={{ textAlign: "right", padding: "10px 12px" }}>Decisions</th>
            <th style={{ textAlign: "right", padding: "10px 12px" }}>Errors</th>
            <th style={{ textAlign: "right", padding: "10px 12px" }}>Tokens</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((s, i) => (
            <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
              <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: "0.8rem" }}>{s.session}</td>
              <td style={{ padding: "10px 12px" }}>{s.agent}</td>
              <td style={{ padding: "10px 12px", textAlign: "right", color: "#34d399" }}>{s.decisions}</td>
              <td style={{ padding: "10px 12px", textAlign: "right", color: s.errors > 0 ? "#f87171" : "#71717a" }}>{s.errors}</td>
              <td style={{ padding: "10px 12px", textAlign: "right" }}>{s.tokens}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: 20, padding: 16, borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)", color: "#71717a", fontSize: "0.85rem" }}>
        Cross-session recall and agent trace visualization will populate from the backend API.
      </div>
    </div>
  );
};

export default AgentTraceViewer;
