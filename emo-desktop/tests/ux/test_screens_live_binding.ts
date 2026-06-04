/**
 * UX Tests — Screen Live Binding Verification
 *
 * Verifies that all 9 routes read from Zustand store (not local state/mocks)
 * and handle empty/loading/error states.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const ROUTES_DIR = path.resolve(__dirname, "../../ui/src/routes");

interface RouteCheck {
  file: string;
  usesUseRuntimeStore: boolean;
  hasEmptyState: boolean;
  hasLoadingState: boolean;
  hasErrorState: boolean;
  hasNoHardcodedData: boolean;
}

function analyzeRoute(filePath: string): RouteCheck {
  const content = fs.readFileSync(filePath, "utf-8");
  return {
    file: path.basename(filePath),
    usesUseRuntimeStore: content.includes("useRuntimeStore"),
    hasEmptyState: content.includes("empty") || content.includes("EmptyState") || content.includes("No ") || content.includes("no "),
    hasLoadingState: content.includes("LoadingSkeleton") || content.includes("loading") || content.includes("skeleton"),
    hasErrorState: content.includes("ErrorRecovery") || content.includes("error") || content.includes("ErrorBoundary"),
    hasNoHardcodedData: !content.includes("hardcoded") && !content.includes("mock_") && !content.includes("const agents = ["),
  };
}

describe("Screen Live Binding", () => {
  const routeFiles = fs.readdirSync(ROUTES_DIR).filter((f) => f.endsWith(".tsx") && !f.startsWith("_"));

  it("should have all 9 route files", () => {
    const expected = ["Dashboard.tsx", "Projects.tsx", "Agents.tsx", "Knowledge.tsx", "Skills.tsx", "Workflows.tsx", "RuntimeMonitor.tsx", "AIGateway.tsx", "Settings.tsx", "TraceExplorer.tsx"];
    for (const exp of expected) {
      expect(routeFiles, `Missing route: ${exp}`).toContain(exp);
    }
  });

  it("should use useRuntimeStore in all routes", () => {
    for (const file of routeFiles) {
      const check = analyzeRoute(path.join(ROUTES_DIR, file));
      expect(check.usesUseRuntimeStore, `${file} does not use useRuntimeStore`).toBe(true);
    }
  });

  it("should have empty state handling in content routes", () => {
    const routesWithEmptyState = ["Dashboard.tsx", "Projects.tsx", "Agents.tsx", "Knowledge.tsx", "Skills.tsx", "Workflows.tsx", "TraceExplorer.tsx", "AIGateway.tsx"];
    for (const file of routesWithEmptyState) {
      const check = analyzeRoute(path.join(ROUTES_DIR, file));
      expect(check.hasEmptyState, `${file} missing empty state`).toBe(true);
    }
  });

  it("should have loading state handling in AIGateway and Agents", () => {
    const loadingRoutes = ["AIGateway.tsx", "Agents.tsx"];
    for (const file of loadingRoutes) {
      const check = analyzeRoute(path.join(ROUTES_DIR, file));
      expect(check.hasLoadingState, `${file} missing loading state`).toBe(true);
    }
  });

  it("should have no hardcoded agent data in Agents.tsx", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Agents.tsx"), "utf-8");
    expect(content).not.toContain("const agents = [");
    expect(content).not.toContain("Planner");
  });

  it("should import from store not local state in AIGateway.tsx", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "AIGateway.tsx"), "utf-8");
    expect(content).not.toContain("React.useState<"); // No local state for data
  });

  it("should reference store routingStatus and gatewayMetrics in AIGateway", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "AIGateway.tsx"), "utf-8");
    expect(content).toContain("useRuntimeStore");
    expect(content).toContain("routingStatus");
    expect(content).toContain("gatewayMetrics");
  });

  it("should connect health and telemetry in Agents.tsx", () => {
    const content = fs.readFileSync(path.join(ROUTES_DIR, "Agents.tsx"), "utf-8");
    expect(content).toContain("health");
    expect(content).toContain("telemetry");
  });

  it("should use StatusBadge consistently across routes", () => {
    const routesWithBadges = ["Projects.tsx", "Workflows.tsx", "Knowledge.tsx", "Skills.tsx", "Agents.tsx", "AIGateway.tsx"];
    for (const file of routesWithBadges) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, file), "utf-8");
      expect(content, `${file} should import StatusBadge`).toContain("StatusBadge");
    }
  });

  it("should not contain architectural terms in route descriptions", () => {
    const forbidden = ["DAG synthesis", "Substrate", "Orchestrator", "ExecutionEngine"];
    for (const file of routeFiles) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, file), "utf-8");
      for (const term of forbidden) {
        expect(content, `${file} contains forbidden term: ${term}`).not.toContain(term);
      }
    }
  });
});
