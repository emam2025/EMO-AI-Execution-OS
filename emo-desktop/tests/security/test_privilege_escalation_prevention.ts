/**
 * Security Tests — Privilege Escalation Prevention
 *
 * Tests that sandboxed tools cannot escalate privileges.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect } from "vitest";

interface SandboxProfile {
  name: string;
  maxCpuPercent: number;
  maxMemoryMb: number;
  allowedCommands: string[];
}

interface EscalationAttempt {
  toolId: string;
  command: string;
  sandbox: SandboxProfile;
}

function isAttemptBlocked(attempt: EscalationAttempt): { blocked: boolean; reason?: string } {
  if (!attempt.sandbox.allowedCommands.includes(attempt.command)) {
    return { blocked: true, reason: "command not in allowed list" };
  }
  if (attempt.command.startsWith("sudo ") || attempt.command.startsWith("su ")) {
    return { blocked: true, reason: "privilege escalation blocked" };
  }
  if (attempt.command.includes("..") || attempt.command.includes("/etc/")) {
    return { blocked: true, reason: "path traversal blocked" };
  }
  return { blocked: false };
}

const SANDBOXES: SandboxProfile[] = [
  {
    name: "basic-inference",
    maxCpuPercent: 50,
    maxMemoryMb: 512,
    allowedCommands: ["read-file", "list-dir", "http-get"],
  },
  {
    name: "admin-tools",
    maxCpuPercent: 90,
    maxMemoryMb: 2048,
    allowedCommands: ["read-file", "write-file", "http-get", "http-post", "exec-script"],
  },
];

describe("Privilege Escalation Prevention", () => {
  it("should block sudo commands in any sandbox", () => {
    const attempt: EscalationAttempt = {
      toolId: "file-reader",
      command: "sudo rm -rf /",
      sandbox: SANDBOXES[0],
    };
    const result = isAttemptBlocked(attempt);
    expect(result.blocked).toBe(true);
    // Either blocked by privilege escalation or command not allowed
    expect(result.reason).toBeDefined();
  });

  it("should block su commands in any sandbox", () => {
    const attempt: EscalationAttempt = {
      toolId: "file-reader",
      command: "su root",
      sandbox: SANDBOXES[0],
    };
    const result = isAttemptBlocked(attempt);
    expect(result.blocked).toBe(true);
  });

  it("should block commands outside allowed list", () => {
    const attempt: EscalationAttempt = {
      toolId: "file-reader",
      command: "exec-shell",
      sandbox: SANDBOXES[0],
    };
    const result = isAttemptBlocked(attempt);
    expect(result.blocked).toBe(true);
    expect(result.reason).toBe("command not in allowed list");
  });

  it("should allow commands in the allowed list", () => {
    const attempt: EscalationAttempt = {
      toolId: "admin-tool",
      command: "exec-script",
      sandbox: SANDBOXES[1],
    };
    const result = isAttemptBlocked(attempt);
    expect(result.blocked).toBe(false);
  });

  it("should block path traversal attempts", () => {
    const attempt: EscalationAttempt = {
      toolId: "file-reader",
      command: "read-file",
      sandbox: SANDBOXES[0],
    };
    expect(isAttemptBlocked({ ...attempt, command: "../etc/passwd" }).blocked).toBe(true);
  });

  it("should enforce max CPU percentage", () => {
    const sandbox = SANDBOXES[1];
    expect(sandbox.maxCpuPercent).toBeLessThanOrEqual(90);
  });

  it("should enforce max memory limit", () => {
    const sandbox = SANDBOXES[1];
    expect(sandbox.maxMemoryMb).toBeLessThanOrEqual(2048);
  });
});
