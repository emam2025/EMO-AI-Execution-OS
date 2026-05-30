import React from "react";
import MemoryDashboard from "./routes/MemoryDashboard";
import ProjectMemoryBrowser from "./routes/ProjectMemoryBrowser";
import ContextBrowser from "./routes/ContextBrowser";
import TraceRecall from "./routes/TraceRecall";
import AgentTraceViewer from "./routes/AgentTraceViewer";
import RetentionSettings from "./routes/RetentionSettings";
import AuditLogViewer from "./routes/AuditLogViewer";

type Route =
  | "dashboard"
  | "project-browser"
  | "context-browser"
  | "trace-recall"
  | "agent-trace"
  | "retention"
  | "audit-log"
  | "settings";

interface AppProps {
  initialRoute?: Route;
}

const NAV: { id: Route; label: string }[] = [
  { id: "dashboard", label: "Dashboard" },
  { id: "project-browser", label: "Project Memory" },
  { id: "context-browser", label: "Context Browser" },
  { id: "trace-recall", label: "Trace Recall" },
  { id: "agent-trace", label: "Agent Trace" },
  { id: "retention", label: "Retention" },
  { id: "audit-log", label: "Audit Log" },
  { id: "settings", label: "Settings" },
];

const ROUTES: Record<Route, React.ReactNode> = {
  dashboard: <MemoryDashboard />,
  "project-browser": <ProjectMemoryBrowser />,
  "context-browser": <ContextBrowser />,
  "trace-recall": <TraceRecall />,
  "agent-trace": <AgentTraceViewer />,
  retention: <RetentionSettings />,
  "audit-log": <AuditLogViewer />,
  settings: <div style={{ color: "#71717a", fontSize: "0.85rem" }}>Settings — memory engine configuration options.</div>,
};

const App: React.FC<AppProps> = ({ initialRoute = "dashboard" }) => {
  const [route, setRoute] = React.useState<Route>(initialRoute);

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        background: "#0f0f13",
        color: "#e4e4e7",
        fontFamily: "Inter, sans-serif",
      }}
    >
      <nav
        style={{
          width: 200,
          padding: 16,
          borderRight: "1px solid rgba(255,255,255,0.06)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            padding: "8px 10px 16px",
            fontWeight: 700,
            fontSize: "1rem",
          }}
        >
          ⊞ Memory OS
        </div>
        {NAV.map((item) => (
          <button
            key={item.id}
            onClick={() => setRoute(item.id)}
            style={{
              display: "block",
              width: "100%",
              padding: "8px 10px",
              borderRadius: 6,
              border: "none",
              background:
                route === item.id
                  ? "rgba(139,92,246,0.15)"
                  : "transparent",
              color: route === item.id ? "#a78bfa" : "#a1a1aa",
              fontWeight: route === item.id ? 600 : 400,
              fontSize: "0.85rem",
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            {item.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <div
          style={{
            padding: "8px 10px",
            fontSize: "0.7rem",
            color: "#52525b",
            borderTop: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          R3 Memory OS · v0.3.0
        </div>
      </nav>
      <main style={{ flex: 1, padding: 24, overflow: "auto" }}>
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, margin: 0 }}>
            {NAV.find((n) => n.id === route)?.label}
          </h1>
        </div>
        {ROUTES[route]}
      </main>
    </div>
  );
};

export default App;
