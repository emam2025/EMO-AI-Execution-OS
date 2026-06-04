/**
 * UX Tests — Design System Consistency
 *
 * Verifies glass-panel, StatusBadge, theme, and state components
 * are used consistently across all routes.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const ROUTES_DIR = path.resolve(__dirname, "../../ui/src/routes");
const DESIGN_DIR = path.resolve(__dirname, "../../ui/src/styles/design-system");

describe("Design System Consistency", () => {
  it("should have all design system component files", () => {
    const files = fs.readdirSync(DESIGN_DIR);
    expect(files).toContain("glass-panel.css");
    expect(files).toContain("smooth-motion.ts");
    expect(files).toContain("status-badge.tsx");
    expect(files).toContain("theme-provider.tsx");
    expect(files).toContain("empty-state.tsx");
    expect(files).toContain("loading-skeleton.tsx");
    expect(files).toContain("error-recovery.tsx");
  });

  it("should use glass-panel class in all routes", () => {
    const routeFiles = fs.readdirSync(ROUTES_DIR).filter((f) => f.endsWith(".tsx"));
    for (const file of routeFiles) {
      const content = fs.readFileSync(path.join(ROUTES_DIR, file), "utf-8");
      expect(content, `${file} missing glass-panel`).toContain("glass-panel");
    }
  });

  it("should have glass-panel CSS with all expected classes", () => {
    const css = fs.readFileSync(path.join(DESIGN_DIR, "glass-panel.css"), "utf-8");
    const expectedClasses = [".glass-panel", ".status-badge", ".metric-card", ".section-header", ".glass-input", ".live-dot"];
    for (const cls of expectedClasses) {
      expect(css, `Missing CSS class: ${cls}`).toContain(cls);
    }
  });

  it("should have dark mode overrides in CSS", () => {
    const css = fs.readFileSync(path.join(DESIGN_DIR, "glass-panel.css"), "utf-8");
    expect(css).toContain('[data-theme="dark"]');
    expect(css).toContain("skeleton-pulse");
  });

  it("should use theme-provider in App.tsx", () => {
    const appContent = fs.readFileSync(path.resolve(__dirname, "../../ui/src/App.tsx"), "utf-8");
    expect(appContent).toContain("ThemeProvider");
    expect(appContent).toContain("useTheme");
  });
});
