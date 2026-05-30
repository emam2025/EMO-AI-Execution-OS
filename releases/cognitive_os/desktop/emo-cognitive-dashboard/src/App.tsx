import React from "react";

type Route = "strategic-planner" | "reflection-log" | "goal-tracker" | "self-eval-report";

const NAV: { id: Route; label: string }[] = [
  { id: "strategic-planner", label: "Strategic Planner" },
  { id: "reflection-log", label: "Reflection Log" },
  { id: "goal-tracker", label: "Goal Tracker" },
  { id: "self-eval-report", label: "Self-Eval Report" },
];

const ROUTE_STUBS: Record<Route, string> = {
  "strategic-planner": "Strategic Planner — decompose goals, evaluate feasibility, generate DAG plans",
  "reflection-log": "Reflection Log — analyse failures, review corrective strategies",
  "goal-tracker": "Goal Tracker — monitor goal lifecycle: Draft → Approved → Executing → Completed",
  "self-eval-report": "Self-Eval Report — plan integrity validation, risk assessment, mitigation plans",
};

const App: React.FC<{ initialRoute?: Route }> = ({ initialRoute = "strategic-planner" }) => {
  const [route, setRoute] = React.useState<Route>(initialRoute);

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0b0b10", color: "#e4e4e7", fontFamily: "Inter, sans-serif" }}>
      <nav style={{ width: 200, padding: 16, borderRight: "1px solid rgba(255,255,255,0.06)" }}>
        <div style={{ padding: "8px 10px 16px", fontWeight: 700, fontSize: "1rem" }}>
          ⊡ Cognitive OS
        </div>
        {NAV.map((item) => (
          <button
            key={item.id}
            onClick={() => setRoute(item.id)}
            style={{
              display: "block", width: "100%", padding: "8px 10px", borderRadius: 6,
              border: "none",
              background: route === item.id ? "rgba(59,130,246,0.15)" : "transparent",
              color: route === item.id ? "#60a5fa" : "#a1a1aa",
              fontWeight: route === item.id ? 600 : 400, fontSize: "0.85rem",
              cursor: "pointer", textAlign: "left",
            }}
          >
            {item.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <div style={{ padding: "8px 10px", fontSize: "0.7rem", color: "#52525b", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          R4 Cognitive OS · v0.0.1 · Foundation Design
        </div>
      </nav>
      <main style={{ flex: 1, padding: 24, overflow: "auto" }}>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, margin: 0 }}>{NAV.find((n) => n.id === route)?.label}</h1>
        <div style={{ marginTop: 24, padding: 32, borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)" }}>
          <p style={{ color: "#71717a", fontSize: "0.9rem" }}>{ROUTE_STUBS[route]}</p>
          <p style={{ color: "#3f3f46", fontSize: "0.8rem", marginTop: 8 }}>
            R4 — Cognitive OS Foundation. Protocols defined. Models validated. Isolation confirmed. Ready for implementation phase.
          </p>
        </div>
      </main>
    </div>
  );
};

export default App;
