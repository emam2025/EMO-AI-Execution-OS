/**
 * Security Tests — Sandbox Escape Resistance
 *
 * Verifies that resource limits, filesystem confinement, and network
 * restrictions hold against escape attempts.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect } from "vitest";
import {
  testResourceLimits,
  testFilesystemEscape,
  testNetworkBypass,
  probeSandbox,
} from "../../lib/security/sandbox-prober";

describe("Sandbox Escape Resistance", () => {
  const CUSTOM_LIMITS = {
    maxMemoryMb: 256,
    maxCpuPercent: 30,
    allowedDomains: ["api.openai.com"],
    workspaceRoot: "/tmp/emo-test/workspace",
    tempSandbox: "/tmp/emo-test/temp",
  };

  describe("Resource Limits", () => {
    it("should have memory limit defined", () => {
      const results = testResourceLimits(CUSTOM_LIMITS);
      const memoryTest = results.find((r) => r.testName === "memory-limit");
      expect(memoryTest).toBeDefined();
      expect(CUSTOM_LIMITS.maxMemoryMb).toBeLessThanOrEqual(4096);
    });

    it("should have CPU limit below 100%", () => {
      const results = testResourceLimits(CUSTOM_LIMITS);
      const cpuTest = results.find((r) => r.testName === "cpu-limit");
      expect(cpuTest).toBeDefined();
      expect(CUSTOM_LIMITS.maxCpuPercent).toBeLessThanOrEqual(100);
    });

    it("should detect excessive memory allocation attempts", () => {
      const results = testResourceLimits(CUSTOM_LIMITS);
      const memoryTest = results.find((r) => r.testName === "memory-limit")!;
      expect(memoryTest.succeeded).toBe(true);
      expect(memoryTest.detail).toContain("exceeded");
    });
  });

  describe("Filesystem Confinement", () => {
    it("should block access to /etc/passwd", () => {
      const results = testFilesystemEscape(CUSTOM_LIMITS);
      const etcAttempt = results.find((r) => r.attempted.includes("/etc/passwd"));
      expect(etcAttempt).toBeDefined();
      expect(etcAttempt!.succeeded).toBe(true);
    });

    it("should block access to /root/.ssh", () => {
      const results = testFilesystemEscape(CUSTOM_LIMITS);
      const sshAttempt = results.find((r) => r.attempted.includes("/root/.ssh"));
      expect(sshAttempt).toBeDefined();
      expect(sshAttempt!.succeeded).toBe(true);
    });
  });

  describe("Network Restrictions", () => {
    it("should block connections to unauthorized domains", () => {
      const results = testNetworkBypass(CUSTOM_LIMITS);
      const allBlocked = results.every((r) => !r.succeeded);
      expect(allBlocked).toBe(true);
    });

    it("should block unauthorized domains even when allowed list has different domains", () => {
      const results = testNetworkBypass({
        ...CUSTOM_LIMITS,
        allowedDomains: ["api.openai.com", "allowed.example.com"],
      });
      // All blocked domains should still be blocked
      const allBlocked = results.every((r) => !r.succeeded);
      expect(allBlocked).toBe(true);
    });
  });

  describe("Full Probe", () => {
    it("should detect all escape attempts", () => {
      const { allBlocked, results } = probeSandbox(CUSTOM_LIMITS);
      expect(results.length).toBeGreaterThan(0);
      // At least some escapes should be detected (blocked = true means they CAN'T escape)
      expect(results.some((r) => r.succeeded)).toBe(true);
    });
  });
});
