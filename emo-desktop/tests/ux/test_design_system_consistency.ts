/**
 * Design System Consistency Tests
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const ROUTES_DIR = path.resolve(__dirname, "../../ui/src/routes");

const ALL_ROUTES = [
  "Dashboard.tsx",
  "Projects.tsx",
  "Agents.tsx",
  "Knowledge.tsx",
  "Skills.tsx",
  "Workflows.tsx",
  "RuntimeMonitor.tsx",
  "AIGateway.tsx",
  "Settings.tsx",
];

describe("Design System Consistency", () => {
  it("all routes use glass-panel class", () => {
    for (const route of ALL_ROUTES) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, route), "utf-8");
      expect(content).toContain("glass-panel");
    }
  });

  it("all routes use section-header for headings", () => {
    const withHeaders = ALL_ROUTES.filter((r) => r !== "Settings.tsx" && r !== "RuntimeMonitor.tsx");
    for (const route of withHeaders) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, route), "utf-8");
      expect(content).toContain("section-header");
    }
  });

  it("status routes use StatusBadge component", () => {
    const withBadges = ["Agents.tsx", "Projects.tsx", "Skills.tsx", "AIGateway.tsx", "Knowledge.tsx", "Workflows.tsx"];
    for (const route of withBadges) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, route), "utf-8");
      expect(content).toContain("StatusBadge");
    }
  });
});
