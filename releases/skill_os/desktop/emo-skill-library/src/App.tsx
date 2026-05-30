import React from "react";

type Route = "skill-browser" | "pattern-viewer" | "evolution-tracker" | "settings";

const NAV: { id: Route; label: string }[] = [
  { id: "skill-browser", label: "Skill Browser" },
  { id: "pattern-viewer", label: "Pattern Viewer" },
  { id: "evolution-tracker", label: "Evolution Tracker" },
  { id: "settings", label: "Settings" },
];

const ROUTE_STUBS: Record<Route, string> = {
  "skill-browser": "Skill Browser — browse extracted skills, filter by tier/domain/confidence",
  "pattern-viewer": "Pattern Viewer — inspect execution blueprints and tool sequences",
  "evolution-tracker": "Evolution Tracker — audit trail of skill promotions and deprecations",
  settings: "Settings — skill extraction thresholds, evolution policy, validator keys",
};

const App: React.FC<{ initialRoute?: Route }> = ({ initialRoute = "skill-browser" }) => {
  const [route, setRoute] = React.useState<Route>(initialRoute);

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0b0b10", color: "#e4e4e7", fontFamily: "Inter, sans-serif" }}>
      <nav style={{ width: 200, padding: 16, borderRight: "1px solid rgba(255,255,255,0.06)" }}>
        <div style={{ padding: "8px 10px 16px", fontWeight: 700, fontSize: "1rem" }}>
          ⊟ Skill OS
        </div>
        {NAV.map((item) => (
          <button
            key={item.id}
            onClick={() => setRoute(item.id)}
            style={{
              display: "block", width: "100%", padding: "8px 10px", borderRadius: 6,
              border: "none",
              background: route === item.id ? "rgba(16,185,129,0.15)" : "transparent",
              color: route === item.id ? "#34d399" : "#a1a1aa",
              fontWeight: route === item.id ? 600 : 400, fontSize: "0.85rem",
              cursor: "pointer", textAlign: "left",
            }}
          >
            {item.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <div style={{ padding: "8px 10px", fontSize: "0.7rem", color: "#52525b", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          R3 Skill OS · v0.0.1 · Foundation Design
        </div>
      </nav>
      <main style={{ flex: 1, padding: 24, overflow: "auto" }}>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, margin: 0 }}>{NAV.find((n) => n.id === route)?.label}</h1>
        <div style={{ marginTop: 24, padding: 32, borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)" }}>
          <p style={{ color: "#71717a", fontSize: "0.9rem" }}>{ROUTE_STUBS[route]}</p>
          <p style={{ color: "#3f3f46", fontSize: "0.8rem", marginTop: 8 }}>
            R3 — Skill OS Foundation. Protocols defined. Models validated. Isolation confirmed. Ready for implementation phase.
          </p>
        </div>
      </main>
    </div>
  );
};

export default App;
