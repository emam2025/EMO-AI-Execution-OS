/**
 * Security Tests — OS Keychain Enforcement
 *
 * Verifies that no plaintext keys exist, tauri-plugin-keyring is active,
 * and all key operations are audited.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  scanForPlaintextKeys,
  ensureTauriKeyringActive,
  verifyKeychainOnly,
  auditKeyStorage,
  getAuditLog,
  clearAuditLog,
} from "../../lib/security/keychain-validator";
import * as fs from "fs";
import * as path from "path";

const PROJECT_ROOT = path.resolve(__dirname, "../..");

describe("OS Keychain Enforcement", () => {
  beforeEach(() => clearAuditLog());
  afterEach(() => clearAuditLog());

  it("should detect no plaintext API keys in the project", () => {
    const findings = scanForPlaintextKeys(PROJECT_ROOT);
    const critical = findings.filter(
      (f) => !f.file.includes("node_modules") && !f.file.includes(".git") && !f.file.includes("/docs/"),
    );
    // If we find keys in test files that use "sk-" as test data, those are intentional
    const testFileKeys = critical.filter((f) => f.file.includes("test_"));
    const sourceKeys = critical.filter((f) => !f.file.includes("test_"));
    // Source should have zero plaintext keys
    expect(sourceKeys.length).toBe(0);
  });

  it("should verify tauri-plugin-keyring is active", () => {
    const result = ensureTauriKeyringActive(PROJECT_ROOT);
    expect(result).toBe(true);
  });

  it("should audit keychain validation events", () => {
    verifyKeychainOnly(PROJECT_ROOT);
    const log = getAuditLog();
    const validateEntries = log.filter((e) => e.action === "validate");
    expect(validateEntries.length).toBeGreaterThanOrEqual(1);
  });

  it("should record store operations in audit log", () => {
    auditKeyStorage("store", "openai", "success");
    const log = getAuditLog();
    expect(log.some((e) => e.action === "store" && e.provider === "openai")).toBe(true);
  });

  it("should record blocked operations in audit log", () => {
    auditKeyStorage("validate", "plaintext-scan", "blocked", "mock finding");
    const log = getAuditLog();
    const blocked = log.filter((e) => e.result === "blocked");
    expect(blocked.length).toBeGreaterThanOrEqual(1);
  });
});
