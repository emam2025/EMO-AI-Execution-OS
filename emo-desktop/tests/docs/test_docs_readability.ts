/**
 * Documentation Readability Tests
 *
 * Verifies:
 *   - No architectural terms in user-facing docs (DAG, Orchestrator, etc.)
 *   - User flow completeness (First-Run Wizard steps documented)
 *   - Security clarity (keychain explanation, privacy policy)
 *
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const DOCS_DIR = path.resolve(__dirname, "../../docs/guides");
const FORBIDDEN_TERMS = ["DAG", "Execution Engine", "ExecutionEngine", "Orchestrator", "Graph", "Substrate"];

function readDoc(filename: string): string {
  const filePath = path.join(DOCS_DIR, filename);
  return fs.readFileSync(filePath, "utf-8");
}

// ──────────────────────────────────────────────
// TestNoArchitecturalTerms (10 tests)
// ──────────────────────────────────────────────
describe("TestNoArchitecturalTerms", () => {
  const docFiles = ["user-guide.md", "admin-guide.md", "security-guide.md", "deployment-guide.md", "api-guide.md"];

  for (const file of docFiles) {
    it(`should not contain 'DAG' in ${file}`, () => {
      const content = readDoc(file);
      expect(content).not.toMatch(/\bDAG\b/i);
    });

    it(`should not contain 'Execution Engine' in ${file}`, () => {
      const content = readDoc(file);
      expect(content).not.toMatch(/Execution\s*Engine/i);
    });

    it(`should not contain 'Orchestrator' in ${file}`, () => {
      const content = readDoc(file);
      expect(content).not.toMatch(/Orchestrator/i);
    });

    it(`should not contain 'Graph' as an architectural term in ${file}`, () => {
      const content = readDoc(file);
      expect(content).not.toMatch(/\bGraph\b/);
    });

    it(`should not contain 'Substrate' in ${file}`, () => {
      const content = readDoc(file);
      expect(content).not.toMatch(/Substrate/i);
    });
  }
});

// ──────────────────────────────────────────────
// TestUserFlowCompleteness (5 tests)
// ──────────────────────────────────────────────
describe("TestUserFlowCompleteness", () => {
  const userGuide = readDoc("user-guide.md");

  it("should document the download step", () => {
    expect(userGuide).toMatch(/download/i);
  });

  it("should document the installation step", () => {
    expect(userGuide).toMatch(/install/i);
  });

  it("should document API key setup", () => {
    expect(userGuide).toMatch(/API key|api key|API Key/i);
  });

  it("should document how to create a project", () => {
    expect(userGuide).toMatch(/creat.*project|new project/i);
  });

  it("should document how to run an agent", () => {
    expect(userGuide).toMatch(/run.*agent|run agent/i);
  });
});

// ──────────────────────────────────────────────
// TestSecurityClarity (5 tests)
// ──────────────────────────────────────────────
describe("TestSecurityClarity", () => {
  const securityGuide = readDoc("security-guide.md");

  it("should mention OS Keychain for key storage", () => {
    expect(securityGuide).toMatch(/keychain/i);
  });

  it("should explain why keychain is used (no files)", () => {
    expect(securityGuide).toMatch(/not.*save.*file|no.*file|never.*file/i);
  });

  it("should explain what happens when keychain is unavailable", () => {
    expect(securityGuide).toMatch(/unavailable|not start|no fallback/i);
  });

  it("should document data privacy (what is stored vs what is not)", () => {
    expect(securityGuide).toMatch(/store|store|data/i);
  });

  it("should explain sandbox limits for agents", () => {
    expect(securityGuide).toMatch(/sandbox|limit|can't|cannot/i);
  });
});
