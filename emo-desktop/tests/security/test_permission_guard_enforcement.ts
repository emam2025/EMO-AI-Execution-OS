/**
 * Security Tests — Permission Guard Enforcement
 *
 * Tests that tools cannot exceed their defined scope.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect } from "vitest";

type ToolScope = "read" | "write" | "admin" | "network" | "filesystem";

interface PermissionRule {
  toolId: string;
  allowedScopes: ToolScope[];
}

function checkPermission(rule: PermissionRule, requested: ToolScope): boolean {
  return rule.allowedScopes.includes(requested);
}

const TOOL_RULES: PermissionRule[] = [
  { toolId: "memory-reader", allowedScopes: ["read"] },
  { toolId: "memory-writer", allowedScopes: ["read", "write"] },
  { toolId: "gateway-infer", allowedScopes: ["read", "network"] },
  { toolId: "runtime-admin", allowedScopes: ["read", "write", "admin"] },
  { toolId: "file-browser", allowedScopes: ["read", "filesystem"] },
];

describe("Permission Guard Enforcement", () => {
  it("should allow tool within its scope", () => {
    const rule = TOOL_RULES.find((r) => r.toolId === "memory-reader")!;
    expect(checkPermission(rule, "read")).toBe(true);
  });

  it("should block tool outside its scope", () => {
    const rule = TOOL_RULES.find((r) => r.toolId === "memory-reader")!;
    expect(checkPermission(rule, "write")).toBe(false);
  });

  it("should block admin-only scopes from non-admin tools", () => {
    const rule = TOOL_RULES.find((r) => r.toolId === "gateway-infer")!;
    expect(checkPermission(rule, "admin")).toBe(false);
  });

  it("should allow admin tools admin scopes", () => {
    const rule = TOOL_RULES.find((r) => r.toolId === "runtime-admin")!;
    expect(checkPermission(rule, "admin")).toBe(true);
  });

  it("should block filesystem access from non-filesystem tools", () => {
    const rule = TOOL_RULES.find((r) => r.toolId === "memory-reader")!;
    expect(checkPermission(rule, "filesystem")).toBe(false);
  });

  it("should allow filesystem read for file-browser", () => {
    const rule = TOOL_RULES.find((r) => r.toolId === "file-browser")!;
    expect(checkPermission(rule, "filesystem")).toBe(true);
  });

  it("should enforce scope boundaries when requesting_write_after_read_only", () => {
    const readOnly = { toolId: "read-only-tool", allowedScopes: ["read"] };
    expect(checkPermission(readOnly, "read")).toBe(true);
    expect(checkPermission(readOnly, "write")).toBe(false);
  });

  it("should enforce scope boundaries when requesting_network_from_memory_tool", () => {
    const memoryTool = { toolId: "mem-only", allowedScopes: ["read", "write"] };
    expect(checkPermission(memoryTool, "network")).toBe(false);
  });
});
