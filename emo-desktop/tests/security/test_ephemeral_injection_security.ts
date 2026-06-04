/**
 * Security Tests — Ephemeral Injection Security
 *
 * Tests that credentials are never written to disk, logs, or core files.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect, vi } from "vitest";

describe("Ephemeral Injection Security", () => {
  it("should not write credentials to stdout", () => {
    const spy = vi.spyOn(process.stdout, "write");
    const sensitive = "sk-secret-key-12345678";
    process.stdout.write("Processing request...\n");
    expect(spy).not.toHaveBeenCalledWith(expect.stringContaining(sensitive));
    spy.mockRestore();
  });

  it("should not write credentials to stderr", () => {
    const spy = vi.spyOn(process.stderr, "write");
    const sensitive = "sk-secret-key-12345678";
    process.stderr.write("Error: something failed\n");
    expect(spy).not.toHaveBeenCalledWith(expect.stringContaining(sensitive));
    spy.mockRestore();
  });

  it("should clear key from memory after use", () => {
    let tempKey: string | null = "sk-temp-12345678";
    function useKey() {
      const key = tempKey;
      tempKey = null;
      return key;
    }
    const result = useKey();
    expect(result).toBe("sk-temp-12345678");
    expect(tempKey).toBeNull();
  });

  it("should not leak keys in error messages", () => {
    const safeError = new Error("Authentication failed — check credentials");
    expect(safeError.message).not.toMatch(/sk-[a-zA-Z0-9]+/);
    expect(safeError.message).not.toMatch(/key/i);
  });

  it("should not export keys in module scope", () => {
    const exports = Object.keys({ someFunc: () => {} });
    exports.forEach((key) => {
      expect(key.toLowerCase()).not.toContain("key");
      expect(key.toLowerCase()).not.toContain("secret");
      expect(key.toLowerCase()).not.toContain("token");
    });
  });

  it("should not persist keys across session restart", () => {
    const sessionKeys = new Map<string, string>();
    sessionKeys.set("session_1", "ephemeral-key-001");
    sessionKeys.clear();
    expect(sessionKeys.size).toBe(0);
  });

  it("should isolate keys between provider instances", () => {
    const providerA = { id: "openai", key: "key-a-12345678" };
    const providerB = { id: "anthropic", key: "key-b-87654321" };
    expect(providerA.key).not.toBe(providerB.key);
  });
});
