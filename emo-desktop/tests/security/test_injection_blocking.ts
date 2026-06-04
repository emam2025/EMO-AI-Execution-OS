/**
 * Security Tests — Command Injection Blocking
 *
 * Verifies that shell metacharacters, path traversal, and system calls
 * are detected and blocked.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  blockCommandInjection,
  sanitizeInput,
  registerToolManifest,
  validateToolScope,
  auditPermissionGrant,
  getPermissionGrants,
  clearPermissionGrants,
  clearInjectionAttempts,
  getInjectionAttempts,
} from "../../lib/security/permission-scanner";

describe("Command Injection Blocking", () => {
  beforeEach(() => {
    clearInjectionAttempts();
    clearPermissionGrants();
  });

  afterEach(() => {
    clearInjectionAttempts();
    clearPermissionGrants();
  });

  it("should block shell metacharacters (;, &&, |)", () => {
    expect(blockCommandInjection("ls; rm -rf /").blocked).toBe(true);
    expect(blockCommandInjection("cmd && echo pwned").blocked).toBe(true);
    expect(blockCommandInjection("cat file | grep secret").blocked).toBe(true);
  });

  it("should block exec and spawn calls", () => {
    expect(blockCommandInjection("exec('malicious')").blocked).toBe(true);
    expect(blockCommandInjection("spawn('shell')").blocked).toBe(true);
  });

  it("should block path traversal", () => {
    expect(blockCommandInjection("../../../etc/passwd").blocked).toBe(true);
    expect(blockCommandInjection("..\\..\\windows\\system32").blocked).toBe(true);
  });

  it("should block sudo escalation", () => {
    expect(blockCommandInjection("sudo rm -rf /").blocked).toBe(true);
    expect(blockCommandInjection("sudo !!").blocked).toBe(true);
  });

  it("should block system path access", () => {
    expect(blockCommandInjection("/etc/passwd").blocked).toBe(true);
    expect(blockCommandInjection("/usr/bin/env").blocked).toBe(true);
  });

  it("should sanitize blocked input", () => {
    const sanitized = sanitizeInput("test; rm -rf / && echo pwned");
    expect(sanitized).not.toContain(";");
    expect(sanitized).not.toContain("&&");
    expect(sanitized).not.toContain("/etc/");
  });
});

describe("Tool Scope Validation", () => {
  beforeEach(() => {
    clearPermissionGrants();
    registerToolManifest({
      toolId: "memory-reader",
      allowedCapabilities: ["memory:read"],
      maxConcurrency: 1,
    });
    registerToolManifest({
      toolId: "gateway-infer",
      allowedCapabilities: ["memory:read", "gateway:infer", "network:outbound"],
      maxConcurrency: 5,
    });
  });

  it("should allow tools within their scope", () => {
    expect(validateToolScope("memory-reader", "memory:read").allowed).toBe(true);
    expect(validateToolScope("gateway-infer", "gateway:infer").allowed).toBe(true);
  });

  it("should block tools outside their scope", () => {
    expect(validateToolScope("memory-reader", "filesystem:write").allowed).toBe(false);
  });

  it("should block unregistered tools", () => {
    expect(validateToolScope("unknown-tool", "memory:read").allowed).toBe(false);
  });

  it("should audit permission grants", () => {
    auditPermissionGrant("memory-reader", "memory:read", true);
    const grants = getPermissionGrants();
    expect(grants.length).toBe(1);
    expect(grants[0].toolId).toBe("memory-reader");
    expect(grants[0].granted).toBe(true);
  });

  it("should audit denied permissions", () => {
    auditPermissionGrant("memory-reader", "filesystem:write", false, "not permitted");
    const grants = getPermissionGrants();
    const denied = grants.filter((g) => !g.granted);
    expect(denied.length).toBeGreaterThanOrEqual(1);
    expect(denied[0].reason).toBe("not permitted");
  });
});
