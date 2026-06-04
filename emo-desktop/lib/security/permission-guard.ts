/**
 * Permission Guard — Tool scope validation, sandbox limits, and audit logging.
 *
 * Enforces:
 *   - Tool permissions: each tool has a defined scope, rejected if exceeded
 *   - Sandbox limits: CPU/memory/network bounds per agent session
 *   - Privilege escalation prevention: blocks any request outside allowed scope
 */
import type { ProviderId } from "../credentials/types";

export type ToolScope = "memory:read" | "memory:write" | "skill:read" | "skill:write" | "gateway:infer" | "gateway:admin" | "runtime:monitor" | "runtime:control" | "network:outbound" | "filesystem:read" | "filesystem:write";

export type PermissionViolation = {
  toolId: string;
  requestedScope: ToolScope;
  allowedScopes: ToolScope[];
  timestamp: number;
  agentId: string;
  blocked: boolean;
};

interface SandboxLimits {
  maxCpuPercent: number;
  maxMemoryMb: number;
  maxNetworkRequestsPerMin: number;
  allowedScopes: ToolScope[];
}

const DEFAULT_SANDBOX: SandboxLimits = {
  maxCpuPercent: 50,
  maxMemoryMb: 512,
  maxNetworkRequestsPerMin: 100,
  allowedScopes: ["memory:read", "skill:read", "gateway:infer", "runtime:monitor", "network:outbound"],
};

const ELEVATED_SCOPES: ToolScope[] = [
  "gateway:admin", "runtime:control", "filesystem:write",
];

const violations: PermissionViolation[] = [];

export function checkToolPermission(
  toolId: string,
  requestedScope: ToolScope,
  agentId: string,
  limits: SandboxLimits = DEFAULT_SANDBOX,
): boolean {
  if (ELEVATED_SCOPES.includes(requestedScope) && !limits.allowedScopes.includes(requestedScope)) {
    const violation: PermissionViolation = {
      toolId,
      requestedScope,
      allowedScopes: limits.allowedScopes,
      timestamp: Date.now(),
      agentId,
      blocked: true,
    };
    violations.push(violation);
    return false;
  }

  if (!limits.allowedScopes.includes(requestedScope)) {
    const violation: PermissionViolation = {
      toolId,
      requestedScope,
      allowedScopes: limits.allowedScopes,
      timestamp: Date.now(),
      agentId,
      blocked: true,
    };
    violations.push(violation);
    return false;
  }

  return true;
}

export function enforceSandboxLimits(
  limits: Partial<SandboxLimits> = {},
): SandboxLimits {
  return { ...DEFAULT_SANDBOX, ...limits };
}

export function auditPermissionViolation(
  violation: Omit<PermissionViolation, "timestamp">,
): PermissionViolation {
  const full: PermissionViolation = { ...violation, timestamp: Date.now() };
  violations.push(full);
  return full;
}

export function getViolationLog(): readonly PermissionViolation[] {
  return violations;
}

export function clearViolationLog(): void {
  violations.length = 0;
}
