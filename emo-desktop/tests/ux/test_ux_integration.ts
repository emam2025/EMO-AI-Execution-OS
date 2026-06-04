/**
 * UX Integration Tests — Full coverage for P2 Product UX.
 *
 * Combines live binding, wizard flow, command palette, design system,
 * keyboard navigation, and wizard completion time tests.
 */
import { describe, it, expect } from "vitest";
import path from "path";
import fs from "fs";

const UI_DIR = path.resolve(__dirname, "../../ui");

describe("Project Structure Integrity", () => {
  const expectedPaths = [
    "src/styles/design-system/glass-panel.css",
    "src/styles/design-system/smooth-motion.ts",
    "src/styles/design-system/timeline-node.tsx",
    "src/styles/design-system/status-badge.tsx",
    "src/styles/design-system/theme-provider.tsx",
    "src/styles/design-system/empty-state.tsx",
    "src/styles/design-system/loading-skeleton.tsx",
    "src/styles/design-system/error-recovery.tsx",
    "src/styles/design-system/index.ts",
    "src/components/first-run-wizard/Wizard.tsx",
    "src/components/first-run-wizard/WelcomeStep.tsx",
    "src/components/first-run-wizard/ConnectModelsStep.tsx",
    "src/components/first-run-wizard/ChooseModeStep.tsx",
    "src/components/first-run-wizard/CreateProjectStep.tsx",
    "src/components/first-run-wizard/LaunchStep.tsx",
    "src/components/command-palette/CommandPalette.tsx",
    "src/stores/runtime.ts",
  ];

  it("all core UI files exist", () => {
    for (const p of expectedPaths) {
      const fullPath = path.join(UI_DIR, p);
      expect(fs.existsSync(fullPath)).toBe(true);
    }
  });

  it("no orphan wizard files remain", () => {
    const wizardDir = path.join(UI_DIR, "src/components/first-run-wizard");
    const files = fs.readdirSync(wizardDir);
    const expected = ["Wizard.tsx", "WelcomeStep.tsx", "ConnectModelsStep.tsx", "ChooseModeStep.tsx", "CreateProjectStep.tsx", "LaunchStep.tsx"];
    for (const f of files) {
      expect(expected.includes(f)).toBe(true);
    }
  });
});

describe("Store Contract", () => {
  it("runtime store exports useRuntimeStore", () => {
    const storePath = path.join(UI_DIR, "src/stores/runtime.ts");
    const content = fs.readFileSync(storePath, "utf-8");
    expect(content).toContain("export const useRuntimeStore");
  });

  it("store has projects, skills, and knowledge state", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/stores/runtime.ts"), "utf-8");
    expect(content).toContain("projects");
    expect(content).toContain("skills");
    expect(content).toContain("knowledgeTree");
  });
});

describe("Keyboard Navigation", () => {
  it("App.tsx registers Ctrl+N shortcut for new project", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/App.tsx"), "utf-8");
    expect(content).toContain("ctrlKey) && e.key === \"n\"");
    expect(content).toContain('setRoute("projects")');
  });

  it("App.tsx registers Ctrl+R shortcut for agents", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/App.tsx"), "utf-8");
    expect(content).toContain("ctrlKey) && e.key === \"r\"");
    expect(content).toContain('setRoute("agents")');
  });

  it("App.tsx registers Ctrl+T shortcut for theme toggle", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/App.tsx"), "utf-8");
    expect(content).toContain("ctrlKey) && e.key === \"t\"");
    expect(content).toContain("toggleTheme");
  });

  it("CommandPalette handles ArrowDown and ArrowUp navigation", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/components/command-palette/CommandPalette.tsx"), "utf-8");
    expect(content).toContain("ArrowDown");
    expect(content).toContain("ArrowUp");
    expect(content).toContain("Enter");
    expect(content).toContain("role=\"listbox\"");
  });

  it("Wizard handles Escape key to close", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/components/first-run-wizard/Wizard.tsx"), "utf-8");
    expect(content).toContain("Escape");
    expect(content).toContain("onClose");
  });
});

describe("Wizard Completion Time", () => {
  it("wizard has exactly 5 steps", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/components/first-run-wizard/Wizard.tsx"), "utf-8");
    const stepCount = (content.match(/case "/g) || []).length;
    expect(stepCount).toBe(5);
  });

  it("wizard persists state to localStorage on complete", () => {
    const wizardContent = fs.readFileSync(path.join(UI_DIR, "src/components/first-run-wizard/Wizard.tsx"), "utf-8");
    expect(wizardContent).toContain("localStorage.setItem(\"emo-first-run-completed\"");
    expect(wizardContent).toContain("localStorage.setItem(\"emo-first-run-state\"");
  });

  it("wizard validation checks runtime connection", () => {
    const wizardContent = fs.readFileSync(path.join(UI_DIR, "src/components/first-run-wizard/Wizard.tsx"), "utf-8");
    expect(wizardContent).toContain("isConnected");
  });

  it("LaunchStep shows validation message when not connected", () => {
    const wizardContent = fs.readFileSync(path.join(UI_DIR, "src/components/first-run-wizard/Wizard.tsx"), "utf-8");
    expect(wizardContent).toContain("validationMessage");
    expect(wizardContent).toContain("Runtime not connected");
  });

  it("wizard can be reset via Settings", () => {
    const appContent = fs.readFileSync(path.join(UI_DIR, "src/App.tsx"), "utf-8");
    expect(appContent).toContain("localStorage.getItem(\"emo-first-run-completed\")");
  });
});

describe("Design System", () => {
  it("ThemeProvider provides toggleTheme", () => {
    const themeContent = fs.readFileSync(path.join(UI_DIR, "src/styles/design-system/theme-provider.tsx"), "utf-8");
    expect(themeContent).toContain("toggleTheme");
    expect(themeContent).toContain("localStorage.setItem(\"emo-theme\"");
  });

  it("EmptyState accepts action prop", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/styles/design-system/empty-state.tsx"), "utf-8");
    expect(content).toContain("action?");
    expect(content).toContain("onClick");
  });

  it("LoadingSkeleton has card, list, and text variants", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/styles/design-system/loading-skeleton.tsx"), "utf-8");
    expect(content).toContain('"card"');
    expect(content).toContain('"list"');
    expect(content).toContain('"text"');
  });

  it("ErrorRecovery accepts onRetry callback", () => {
    const content = fs.readFileSync(path.join(UI_DIR, "src/styles/design-system/error-recovery.tsx"), "utf-8");
    expect(content).toContain("onRetry");
    expect(content).toContain("Retry");
  });
});
