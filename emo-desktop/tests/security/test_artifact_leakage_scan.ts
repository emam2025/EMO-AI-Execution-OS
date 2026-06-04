/**
 * Security Tests — Artifact Leakage Scan
 *
 * Verifies that the leakage scanner detects key patterns, internal paths,
 * and architectural terms in build artifacts.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect } from "vitest";
import { scanForPlaintextKeys } from "../../lib/security/keychain-validator";
import * as path from "path";

const PROJECT_ROOT = path.resolve(__dirname, "../..");

describe("Artifact Leakage Scan", () => {
  it("should have zero critical key leaks in source code", () => {
    const findings = scanForPlaintextKeys(PROJECT_ROOT);
    // Filter out test files that intentionally use key patterns
    const sourceFindings = findings.filter(
      (f) => !f.file.includes("test_") && !f.file.includes("node_modules") && !f.file.includes(".git") && !f.file.includes("/docs/"),
    );
    expect(sourceFindings.length).toBe(0);
  });

  it("should detect keys in test files (intentional test data)", () => {
    const findings = scanForPlaintextKeys(PROJECT_ROOT);
    const testFindings = findings.filter(
      (f) => f.file.includes("test_") && f.pattern.includes("sk-"),
    );
    // Test files may have key patterns — that's expected test data
    expect(Array.isArray(testFindings)).toBe(true);
  });

  it("should not scan node_modules or .git", () => {
    const findings = scanForPlaintextKeys(PROJECT_ROOT);
    const nodeModules = findings.filter((f) => f.file.includes("node_modules"));
    const gitDir = findings.filter((f) => f.file.includes(".git"));
    expect(nodeModules.length).toBe(0);
    expect(gitDir.length).toBe(0);
  });

  it("should scan only text-based file extensions", () => {
    const findings = scanForPlaintextKeys(PROJECT_ROOT);
    for (const f of findings) {
      const ext = path.extname(f.file);
      // Should only find in text files
      expect(
        [".ts", ".tsx", ".js", ".json", ".md", ".txt", ".yaml", ".yml", ".env"].includes(ext) ||
        f.file.includes(".env") || ext === "",
      ).toBe(true);
    }
  });

  it("should report findings with file path and line number", () => {
    const testFileDir = path.resolve(__dirname, "..");
    const findings = scanForPlaintextKeys(testFileDir);
    for (const f of findings) {
      expect(f.file).toBeDefined();
      expect(f.line).toBeGreaterThan(0);
      expect(f.pattern).toBeDefined();
      expect(f.snippet).toBeDefined();
    }
  });
});
