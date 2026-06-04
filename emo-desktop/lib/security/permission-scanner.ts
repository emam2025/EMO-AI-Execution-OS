/**
 * Permission Scanner — Tool scope validation & injection blocking
 *
 * Enforces:
 *   - Every tool has a registered CapabilityManifest with allowed scopes
 *   - No tool may execute outside its declared scope
 *   - All user/tool input is filtered for command injection patterns
 *   - Every permission grant is logged with timestamp + audit signature
 */
import type { ProviderId } from "../credentials/types";

// ──────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────

export type ToolCapability = "memory:read" | "memory:write" | "skill:read" | "skill:write" | "gateway:infer" | "gateway:admin" | "runtime:monitor" | "runtime:control" | "network:outbound" | "filesystem:read" | "filesystem:write";

export interface CapabilityManifest {
  toolId: string;
  allowedCapabilities: ToolCapability[];
  maxConcurrency: number;
}

export interface PermissionGrant {
  grantId: string;
  toolId: string;
  capability: ToolCapability;
  timestamp: number;
  granted: boolean;
  reason?: string;
}

export interface InjectionAttempt {
  input: string;
  blocked: boolean;
  matchedPattern: string | null;
  timestamp: number;
}

// ──────────────────────────────────────────────
// Injection patterns
// ──────────────────────────────────────────────

const INJECTION_PATTERNS = [
  { pattern: /[;|&`$]/g, name: "shell-metacharacter" },
  { pattern: /\bexec\s*\(/gi, name: "exec-call" },
  { pattern: /\bspawn\s*\(/gi, name: "spawn-call" },
  { pattern: /\.\.\/|\.\.\\/g, name: "path-traversal" },
  { pattern: /\/etc\/|\/usr\/|\/bin\/|\/boot\//g, name: "system-path" },
  { pattern: /sudo\s+/gi, name: "sudo-escalation" },
  { pattern: /\/proc\/|\/sys\//g, name: "kernel-path" },
];

// ──────────────────────────────────────────────
// State
// ──────────────────────────────────────────────

const registeredManifests = new Map<string, CapabilityManifest>();
const permissionGrants: PermissionGrant[] = [];
const injectionAttempts: InjectionAttempt[] = [];

let grantCounter = 0;

// ──────────────────────────────────────────────
// Manifest registration
// ──────────────────────────────────────────────

export function registerToolManifest(manifest: CapabilityManifest): void {
  registeredManifests.set(manifest.toolId, manifest);
}

export function getToolManifest(toolId: string): CapabilityManifest | undefined {
  return registeredManifests.get(toolId);
}

export function clearManifests(): void {
  registeredManifests.clear();
}

// ──────────────────────────────────────────────
// Scope validation
// ──────────────────────────────────────────────

export function validateToolScope(
  toolId: string,
  requestedCapability: ToolCapability,
): { allowed: boolean; reason?: string } {
  const manifest = registeredManifests.get(toolId);

  if (!manifest) {
    return { allowed: false, reason: `tool ${toolId} has no registered manifest` };
  }

  if (!manifest.allowedCapabilities.includes(requestedCapability)) {
    return { allowed: false, reason: `${toolId} not permitted for ${requestedCapability}` };
  }

  return { allowed: true };
}

// ──────────────────────────────────────────────
// Permission grant audit
// ──────────────────────────────────────────────

export function auditPermissionGrant(
  toolId: string,
  capability: ToolCapability,
  granted: boolean,
  reason?: string,
): PermissionGrant {
  const grant: PermissionGrant = {
    grantId: `pg-${++grantCounter}-${Date.now()}`,
    toolId,
    capability,
    timestamp: Date.now(),
    granted,
    reason,
  };
  permissionGrants.push(grant);
  return grant;
}

export function getPermissionGrants(): readonly PermissionGrant[] {
  return permissionGrants;
}

export function clearPermissionGrants(): void {
  permissionGrants.length = 0;
}

// ──────────────────────────────────────────────
// Injection blocking
// ──────────────────────────────────────────────

export function blockCommandInjection(input: string): { blocked: boolean; matchedPattern: string | null } {
  for (const { pattern, name } of INJECTION_PATTERNS) {
    pattern.lastIndex = 0;
    if (pattern.test(input)) {
      const attempt: InjectionAttempt = {
        input: input.slice(0, 100),
        blocked: true,
        matchedPattern: name,
        timestamp: Date.now(),
      };
      injectionAttempts.push(attempt);
      return { blocked: true, matchedPattern: name };
    }
  }
  return { blocked: false, matchedPattern: null };
}

export function getInjectionAttempts(): readonly InjectionAttempt[] {
  return injectionAttempts;
}

export function clearInjectionAttempts(): void {
  injectionAttempts.length = 0;
}

// ──────────────────────────────────────────────
// Input sanitization
// ──────────────────────────────────────────────

export function sanitizeInput(input: string): string {
  return input
    .replace(/[;|&`$]/g, "")
    .replace(/\.\./g, "")
    .replace(/\/etc\/|\/usr\/|\/bin\//g, "")
    .trim();
}
