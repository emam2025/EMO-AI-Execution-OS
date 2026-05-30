/**
 * Test: UI Routing Completeness
 *
 * Verifies that all 7 skeleton routes exist, plus the Memory Explorer
 * Coming Soon stub. Ensures no route is missing.
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const ROUTES_DIR = path.resolve(__dirname, "../ui/src/routes");
const EXPECTED_ROUTES = [
  "Dashboard.tsx",
  "AgentStudio.tsx",
  "ProjectCenter.tsx",
  "RuntimeMonitor.tsx",
  "TraceExplorer.tsx",
  "MemoryExplorer.tsx",
  "Settings.tsx",
  "ModelGateway.tsx",
];

const COMING_SOON_ROUTES = ["MemoryExplorer.tsx"];

describe("UI Routing Completeness", () => {
  it("all 8 route files exist", () => {
    for (const route of EXPECTED_ROUTES) {
      const filePath = path.join(ROUTES_DIR, route);
      expect(fs.existsSync(filePath)).toBe(true);
    }
  });

  it("has exactly 8 route files", () => {
    const files = fs.readdirSync(ROUTES_DIR).filter((f) => f.endsWith(".tsx"));
    expect(files.length).toBe(EXPECTED_ROUTES.length);
  });

  it("MemoryExplorer shows Coming Soon stub", () => {
    const content = fs.readFileSync(
      path.join(ROUTES_DIR, "MemoryExplorer.tsx"),
      "utf-8"
    );
    expect(content).toContain("Coming Soon");
    expect(content).toContain("Read Only");
    expect(content).not.toContain("fake");
    expect(content).not.toContain("mock data");
  });

  it("no Coming Soon routes contain runtime logic", () => {
    for (const route of COMING_SOON_ROUTES) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, route), "utf-8");
      expect(content).not.toContain("useRuntimeStore");
      expect(content).not.toContain("RuntimeClient");
    }
  });

  it("each route exports a React component", () => {
    for (const route of EXPECTED_ROUTES) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, route), "utf-8");
      expect(content).toMatch(/export const \w+:\s*React\.FC/);
    }
  });
});
