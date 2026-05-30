import React, { useEffect } from "react";
import { useRuntimeStore } from "./stores/runtime";
import { injectMotionKeyframes } from "./styles/design-system/smooth-motion";
import { CommandPalette } from "./components/command-palette/CommandPalette";
import { FirstRunWizard } from "./components/first-run-wizard/Wizard";
import "./styles/design-system/glass-panel.css";

type Route = "dashboard" | "projects" | "agents" | "knowledge" | "skills" | "workflows" | "runtime-monitor" | "settings" | "ai-gateway";

interface AppProps {
  initialRoute?: Route;
}

const NAV_ITEMS: { id: Route; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "◉" },
  { id: "projects", label: "Projects", icon: "▤" },
  { id: "agents", label: "Agents", icon: "◇" },
  { id: "knowledge", label: "Knowledge", icon: "◎" },
  { id: "skills", label: "Skills", icon: "⚡" },
  { id: "workflows", label: "Workflows", icon: "◈" },
  { id: "runtime-monitor", label: "Runtime", icon: "⊞" },
  { id: "ai-gateway", label: "AI Gateway", icon: "⚙" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

const App: React.FC<AppProps> = ({ initialRoute = "dashboard" }) => {
  const [route, setRoute] = React.useState<Route>(initialRoute);
  const [wizardOpen, setWizardOpen] = React.useState(false);
  const { session, isConnected } = useRuntimeStore();

  useEffect(() => {
    injectMotionKeyframes();
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
      case "projects":
        return <ProjectsPage />;
      case "agents":
        return <AgentsPage />;
      case "knowledge":
        return <KnowledgePage />;
      case "skills":
        return <SkillsPage />;
      case "workflows":
        return <WorkflowsPage />;
      case "runtime-monitor":
        return <RuntimeMonitorPage />;
      case "ai-gateway":
        return <AIGatewayPage />;
      case "settings":
        return <SettingsPage onNavigate={setRoute} />;
    }
  };

  return (
    <div style={{ display: "flex", height: "100vh", background: "#f5f5f7", fontFamily: "Inter, -apple-system, sans-serif" }}>
      <nav className="glass-panel" style={{ width: 220, padding: 16, display: "flex", flexDirection: "column", gap: 4, borderRadius: 0, borderRight: "1px solid rgba(0,0,0,0.06)" }}>
        <div style={{ padding: "8px 10px 16px", fontWeight: 700, fontSize: "1rem", letterSpacing: "-0.02em", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: "1.2rem" }}>⟁</span>
          EMO AI
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
          v1.0.0 · {isConnected ? "Live" : "Disconnected"}
        </div>
      </nav>

      <main style={{ flex: 1, overflow: "auto", padding: 0 }}>
        {renderRoute()}
      </main>

      <CommandPalette onNavigate={setRoute} />
      {wizardOpen && <FirstRunWizard onComplete={handleWizardComplete} onClose={() => setWizardOpen(false)} />}
    </div>
  );
};

import { Dashboard as DashboardPage } from "./routes/Dashboard";
import { Projects as ProjectsPage } from "./routes/Projects";
import { Agents as AgentsPage } from "./routes/Agents";
import { Knowledge as KnowledgePage } from "./routes/Knowledge";
import { Skills as SkillsPage } from "./routes/Skills";
import { Workflows as WorkflowsPage } from "./routes/Workflows";
import { RuntimeMonitor as RuntimeMonitorPage } from "./routes/RuntimeMonitor";
import { AIGateway as AIGatewayPage } from "./routes/AIGateway";
import { Settings as SettingsPage } from "./routes/Settings";

export default App;
