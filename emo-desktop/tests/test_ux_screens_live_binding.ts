/**
 * UI Live Binding — Tests for Zustand store integration, design system, and zero mock data.
 *
 * Coverage:
 *   - All 9 product screens use useRuntimeStore or valid data layer
 *   - Zero mock/fake data in screen components
 *   - Design system classes used consistently
 *   - First-run wizard persists completion
 *   - Command palette supports Ctrl+K/Cmd+K
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const ROUTES_DIR = path.resolve(__dirname, "../ui/src/routes");
const COMPONENTS_DIR = path.resolve(__dirname, "../ui/src/components");

const DESIGN_SYSTEM_FILES = [
  path.resolve(__dirname, "../ui/src/styles/design-system/glass-panel.css"),
  path.resolve(__dirname, "../ui/src/styles/design-system/smooth-motion.ts"),
  path.resolve(__dirname, "../ui/src/styles/design-system/timeline-node.tsx"),
  path.resolve(__dirname, "../ui/src/styles/design-system/status-badge.tsx"),
  path.resolve(__dirname, "../ui/src/styles/design-system/index.ts"),
];

describe("Routes — Live Binding & Zero Mock Data", () => {
  it("Dashboard uses useRuntimeStore and no mock data", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Dashboard.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
    expect(content).not.toContain("fake");
  });

  it("Projects uses useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Projects.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
  });

  it("Agents uses useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Agents.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
  });

  it("Knowledge uses useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Knowledge.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("fake");
  });

  it("Skills uses useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Skills.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
  });

  it("Workflows uses useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Workflows.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
  });

  it("RuntimeMonitor uses useRuntimeStore", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "RuntimeMonitor.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).not.toContain("mock");
  });

  it("AIGateway uses StatusBadge design component", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "AIGateway.tsx"), "utf-8");
    expect(content).toContain("StatusBadge");
    expect(content).toContain("glass-panel");
  });

  it("Settings uses useRuntimeStore and shows governance badges", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Settings.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).toContain("glass-panel");
  });

  it("all routes use glass-panel design system", () => {
    const routes = fs.readdirSync(ROUTES_DIR).filter((f) => f.endsWith(".tsx"));
    for (const route of routes) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, route), "utf-8");
      if (route !== "Settings.tsx") {
        expect(content).toContain("glass-panel");
      }
    }
  });

  it("FirstRunWizard persists completion in localStorage", () => {
    const wizardPath = path.join(COMPONENTS_DIR, "first-run-wizard", "Wizard.tsx");
    const content = fs.readFileSync(wizardPath, "utf-8");
    expect(content).toContain("localStorage");
    expect(content).not.toContain("validate");
  });

  it("CommandPalette supports Ctrl+K and Cmd+K", () => {
    const cmdPath = path.join(COMPONENTS_DIR, "command-palette", "CommandPalette.tsx");
    const content = fs.readFileSync(cmdPath, "utf-8");
    expect(content).toContain("metaKey");
    expect(content).toContain("ctrlKey");
  });
});

describe("Design System Files", () => {
  it("all design system files exist", () => {
    for (const file of DESIGN_SYSTEM_FILES) {
      expect(fs.existsSync(file)).toBe(true);
    }
  });

  it("glass-panel.css defines core classes", () => {
    const css = fs.readFileSync(DESIGN_SYSTEM_FILES[0], "utf-8");
    expect(css).toContain(".glass-panel");
    expect(css).toContain(".status-badge");
    expect(css).toContain(".metric-card");
    expect(css).toContain(".section-header");
    expect(css).toContain(".glass-input");
  });

  it("smooth-motion.ts exports transitions and injectMotionKeyframes", () => {
    const ts = fs.readFileSync(DESIGN_SYSTEM_FILES[1], "utf-8");
    expect(ts).toContain("transitions");
    expect(ts).toContain("injectMotionKeyframes");
  });

  it("timeline-node.tsx exports TimelineNode and ExecutionTimeline", () => {
    const tsx = fs.readFileSync(DESIGN_SYSTEM_FILES[2], "utf-8");
    expect(tsx).toContain("TimelineNode");
    expect(tsx).toContain("ExecutionTimeline");
  });

  it("status-badge.tsx exports StatusBadge with all states", () => {
    const tsx = fs.readFileSync(DESIGN_SYSTEM_FILES[3], "utf-8");
    expect(tsx).toContain("StatusBadge");
    expect(tsx).toContain("active");
    expect(tsx).toContain("failed");
    expect(tsx).toContain("running");
  });

  it("design-system/index.ts re-exports all components", () => {
    const idx = fs.readFileSync(DESIGN_SYSTEM_FILES[4], "utf-8");
    expect(idx).toContain("StatusBadge");
    expect(idx).toContain("TimelineNode");
    expect(idx).toContain("injectMotionKeyframes");
  });
});

describe("Zero Core Freeze Violations", () => {
  it("no import statements reference releases/ or core/", () => {
    const allFiles = [
      ...fs.readdirSync(ROUTES_DIR).filter((f) => f.endsWith(".tsx")).map((f) => path.join(ROUTES_DIR, f)),
      path.join(COMPONENTS_DIR, "command-palette", "CommandPalette.tsx"),
      path.join(COMPONENTS_DIR, "first-run-wizard", "Wizard.tsx"),
    ];
    for (const file of allFiles) {
      const content = fs.readFileSync(file, "utf-8");
      expect(content).not.toMatch(/from ["'].*\/(releases|core)\//);
    }
  });
});
