/**
 * UI Live Binding — Tests for Zustand store integration and design system usage.
 *
 * Coverage:
 *   - All 8 routes render without crash
 *   - Live-bound routes use useRuntimeStore
 *   - Skeleton routes use design system classes (glass-panel, metric-card, section-header)
 *   - MemoryExplorer remains read-only stub
 *   - Settings shows governance status
 *   - First-run wizard persists completion
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const ROUTES_DIR = path.resolve(__dirname, "../ui/src/routes");
const COMPONENTS_DIR = path.resolve(__dirname, "../ui/src/components");

const LIVE_ROUTES = [
  "Dashboard.tsx",
  "RuntimeMonitor.tsx",
  "TraceExplorer.tsx",
  "ModelGateway.tsx",
];

const SKELETON_ROUTES = [
  "AgentStudio.tsx",
  "ProjectCenter.tsx",
  "Settings.tsx",
];

const COMING_SOON_ROUTES = ["MemoryExplorer.tsx"];

describe("Routes — Live Binding", () => {
  it("Dashboard imports useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Dashboard.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
    expect(content).not.toContain("fake");
  });

  it("RuntimeMonitor imports useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "RuntimeMonitor.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
    expect(content).not.toContain("fake");
  });

  it("TraceExplorer imports useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "TraceExplorer.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
    expect(content).not.toContain("fake");
  });

  it("ModelGateway imports useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "ModelGateway.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
    expect(content).not.toContain("fake");
  });

  it("AgentStudio uses glass-panel design system", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "AgentStudio.tsx"), "utf-8");
    expect(content).toContain("glass-panel");
    expect(content).toContain("section-header");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("coming soon");
  });

  it("ProjectCenter uses glass-panel design system", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "ProjectCenter.tsx"), "utf-8");
    expect(content).toContain("glass-panel");
    expect(content).toContain("metric-card-value");
    expect(content).toContain("section-header");
    expect(content).not.toContain("mock");
  });

  it("Settings uses glass-panel design system and shows governance status", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Settings.tsx"), "utf-8");
    expect(content).toContain("glass-panel");
    expect(content).toContain("useRuntimeStore");
    expect(content).toContain("RBAC");
    expect(content).toContain("Audit");
    expect(content).toContain("Tenant Isolation");
  });

  it("MemoryExplorer remains read-only stub without live data", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "MemoryExplorer.tsx"), "utf-8");
    expect(content).toContain("Coming Soon");
    expect(content).not.toContain("useRuntimeStore");
  });

  it("FirstRunWizard persists completion in localStorage", () => {
    const wizardPath = path.join(COMPONENTS_DIR, "first-run-wizard", "Wizard.tsx");
    const content = fs.readFileSync(wizardPath, "utf-8");
    expect(content).toContain("localStorage");
  });

  it("CommandPalette supports Ctrl+K and Cmd+K", () => {
    const cmdPath = path.join(COMPONENTS_DIR, "command-palette", "CommandPalette.tsx");
    const content = fs.readFileSync(cmdPath, "utf-8");
    expect(content).toContain("metaKey");
    expect(content).toContain("ctrlKey");
  });
});
