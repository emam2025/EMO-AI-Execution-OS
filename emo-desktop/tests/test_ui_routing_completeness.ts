/**
 * Test: UI Routing Completeness — 9 Product Screens
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const ROUTES_DIR = path.resolve(__dirname, "../ui/src/routes");
const EXPECTED_ROUTES = [
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

describe("UI Routing Completeness — 9 Screens", () => {
  it("all 9 route files exist", () => {
    for (const route of EXPECTED_ROUTES) {
      const filePath = path.join(ROUTES_DIR, route);
      expect(fs.existsSync(filePath)).toBe(true);
    }
  });

  it("each route exports a React component", () => {
    for (const route of EXPECTED_ROUTES) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, route), "utf-8");
      expect(content).toMatch(/export const \w+:\s*React\.FC/);
    }
  });

  it("no route imports from releases/ or core/", () => {
    for (const route of EXPECTED_ROUTES) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, route), "utf-8");
      expect(content).not.toMatch(/from ["'].*\/(releases|core)\//);
    }
  });
});
