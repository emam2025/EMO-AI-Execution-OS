import React, { useEffect } from "react";
import { useRuntimeStore } from "./stores/runtime";
import { injectMotionKeyframes } from "./styles/design-system/smooth-motion";
import { CommandPalette } from "./components/command-palette/CommandPalette";
import { FirstRunWizard } from "./components/first-run-wizard/Wizard";
import "./styles/design-system/glass-panel.css";

type Route = "dashboard" | "runtime-monitor" | "trace-explorer" | "model-gateway" | "agent-studio" | "project-center" | "settings" | "memory-explorer";

interface AppProps {
  initialRoute?: Route;
}

const NAV_ITEMS: { id: Route; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "◉" },
  { id: "runtime-monitor", label: "Runtime Monitor", icon: "⚡" },
  { id: "trace-explorer", label: "Trace Explorer", icon: "◈" },
  { id: "model-gateway", label: "Model Gateway", icon: "⊞" },
  { id: "agent-studio", label: "Agent Studio", icon: "◇" },
  { id: "project-center", label: "Project Center", icon: "▤" },
  { id: "settings", label: "Settings", icon: "⚙" },
  { id: "memory-explorer", label: "Memory Explorer", icon: "◎" },
];

const App: React.FC<AppProps> = ({ initialRoute = "dashboard" }) => {
  const [route, setRoute] = React.useState<Route>(initialRoute);
  const [wizardOpen, setWizardOpen] = React.useState(false);
  const { session, isConnected } = useRuntimeStore();

  useEffect(() => {
    injectMotionKeyframes();
    // Check if first run
    const completed = localStorage.getItem("emo-first-run-completed");
    if (!completed) {
      setWizardOpen(true);
    }
  }, []);

  const handleWizardComplete = () => {
    localStorage.setItem("emo-first-run-completed", "true");
    setWizardOpen(false);
  };

  const renderRoute = () => {
    switch (route) {
      case "dashboard":
        return <DashboardPage onNavigate={setRoute} />;
      case "runtime-monitor":
        return <RuntimeMonitorPage />;
      case "trace-explorer":
        return <TraceExplorerPage />;
      case "model-gateway":
        return <ModelGatewayPage />;
      case "agent-studio":
        return <AgentStudioPage />;
      case "project-center":
        return <ProjectCenterPage />;
      case "settings":
        return <SettingsPage onNavigate={setRoute} />;
      case "memory-explorer":
        return <MemoryExplorerPage />;
    }
  };

  return (
    <div style={{ display: "flex", height: "100vh", background: "#f5f5f7", fontFamily: "Inter, -apple-system, sans-serif" }}>
      {/* Sidebar */}
      <nav className="glass-panel" style={{ width: 220, padding: 16, display: "flex", flexDirection: "column", gap: 4, borderRadius: 0, borderRight: "1px solid rgba(0,0,0,0.06)" }}>
        <div style={{ padding: "8px 10px 16px", fontWeight: 700, fontSize: "1rem", letterSpacing: "-0.02em", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: "1.2rem" }}>⟁</span>
          EMO OS
          {isConnected && <span className="live-dot" />}
        </div>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            onClick={() => setRoute(item.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 10px",
              borderRadius: 8,
              border: "none",
              background: route === item.id ? "rgba(59,130,246,0.1)" : "transparent",
              color: route === item.id ? "#2563eb" : "#374151",
              fontWeight: route === item.id ? 600 : 400,
              fontSize: "0.85rem",
              cursor: "pointer",
              transition: "all 0.12s ease-out",
            }}
          >
            <span style={{ fontSize: "0.9rem", width: 18, textAlign: "center" }}>{item.icon}</span>
            {item.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <div style={{ padding: "8px 10px", fontSize: "0.7rem", color: "#9ca3af", borderTop: "1px solid rgba(0,0,0,0.06)" }}>
          v0.1.3-product-alpha · {isConnected ? "Live" : "Disconnected"}
        </div>
      </nav>

      {/* Main */}
      <main style={{ flex: 1, overflow: "auto", padding: 0 }}>
        {renderRoute()}
      </main>

      {/* Global Command Palette */}
      <CommandPalette onNavigate={setRoute} />

      {/* First-Run Wizard */}
      {wizardOpen && <FirstRunWizard onComplete={handleWizardComplete} onClose={() => setWizardOpen(false)} />}
    </div>
  );
};

// Lazy imports to keep App.tsx clean
import { Dashboard as DashboardPage } from "./routes/Dashboard";
import { RuntimeMonitor as RuntimeMonitorPage } from "./routes/RuntimeMonitor";
import { TraceExplorer as TraceExplorerPage } from "./routes/TraceExplorer";
import { ModelGateway as ModelGatewayPage } from "./routes/ModelGateway";
import { AgentStudio as AgentStudioPage } from "./routes/AgentStudio";
import { ProjectCenter as ProjectCenterPage } from "./routes/ProjectCenter";
import { Settings as SettingsPage } from "./routes/Settings";
import { MemoryExplorer as MemoryExplorerPage } from "./routes/MemoryExplorer";

export default App;
