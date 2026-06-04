import { createHash, randomBytes } from "crypto";
import { logAuditEvent } from "../security/audit-logger";
import { validateLicense } from "../portal/license-manager";

export type BetaStatus = "PENDING" | "ACTIVE" | "SUSPENDED" | "REVOKED";
export type BetaRole = "tester" | "admin" | "viewer" | "security-auditor";

export interface BetaUser {
  id: string;
  email: string;
  company: string;
  role: BetaRole;
  status: BetaStatus;
  licenseKey: string;
  createdAt: number;
  lastActivity: number | null;
  activatedAt: number | null;
  suspendedAt: number | null;
  metadata: Record<string, unknown>;
}

export interface BetaSession {
  token: string;
  userId: string;
  role: BetaRole;
  issuedAt: number;
  expiresAt: number;
  licenseValid: boolean;
}

export interface BetaRegistrationResult {
  user: BetaUser | null;
  created: boolean;
  reason?: string;
}

export interface SessionValidation {
  valid: boolean;
  session?: BetaSession;
  reason?: string;
}

export interface RevocationResult {
  revoked: boolean;
  reason?: string;
}

const users = new Map<string, BetaUser>();
const sessions = new Map<string, BetaSession>();
const SESSION_DURATION_MS = 24 * 60 * 60 * 1000;
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function generateId(): string {
  return "beta_" + randomBytes(16).toString("hex").slice(0, 16);
}

function generateToken(): string {
  return "bet_" + randomBytes(24).toString("hex") + "_" + Date.now().toString(36);
}

export function registerBetaUser(
  email: string,
  company: string,
  role: BetaRole,
  licenseKey?: string,
): BetaRegistrationResult {
  if (!email || !EMAIL_REGEX.test(email)) {
    return { user: null, created: false, reason: "invalid email address" };
  }
  if (!company || company.length < 2) {
    return { user: null, created: false, reason: "company name too short" };
  }
  const validRoles: BetaRole[] = ["tester", "admin", "viewer", "security-auditor"];
  if (!validRoles.includes(role)) {
    return { user: null, created: false, reason: "invalid role" };
  }
  for (const existing of users.values()) {
    if (existing.email.toLowerCase() === email.toLowerCase()) {
      return { user: null, created: false, reason: "email already registered" };
    }
  }
  if (licenseKey) {
    const validation = validateLicense(licenseKey);
    if (!validation.valid) {
      return { user: null, created: false, reason: `license validation failed: ${validation.reason}` };
    }
  }
  const id = generateId();
  const now = Date.now();
  const user: BetaUser = {
    id,
    email: email.toLowerCase(),
    company,
    role,
    status: "PENDING",
    licenseKey: licenseKey || "",
    createdAt: now,
    lastActivity: null,
    activatedAt: null,
    suspendedAt: null,
    metadata: {},
  };
  users.set(id, user);
  logAuditEvent({
    type: "permission_violation",
    severity: "low",
    source: "beta-user-manager",
    detail: `Beta user registered: ${email} for ${company} as ${role}`,
    metadata: { userId: id, status: "PENDING" },
  });
  return { user, created: true };
}

export function activateBetaUser(userId: string): BetaRegistrationResult {
  const user = users.get(userId);
  if (!user) {
    return { user: null, created: false, reason: "user not found" };
  }
  if (user.status !== "PENDING") {
    return { user: null, created: false, reason: `cannot activate user with status ${user.status}` };
  }
  user.status = "ACTIVE";
  user.activatedAt = Date.now();
  logAuditEvent({
    type: "permission_violation",
    severity: "low",
    source: "beta-user-manager",
    detail: `Beta user activated: ${user.email}`,
    metadata: { userId },
  });
  return { user, created: true };
}

export function issueBetaSession(userId: string): BetaSession | null {
  const user = users.get(userId);
  if (!user || user.status !== "ACTIVE") {
    return null;
  }
  const now = Date.now();
  const token = generateToken();
  const session: BetaSession = {
    token,
    userId,
    role: user.role,
    issuedAt: now,
    expiresAt: now + SESSION_DURATION_MS,
    licenseValid: true,
  };
  sessions.set(token, session);
  user.lastActivity = now;
  return session;
}

export function validateBetaSession(token: string): SessionValidation {
  const session = sessions.get(token);
  if (!session) {
    return { valid: false, reason: "session not found" };
  }
  if (Date.now() > session.expiresAt) {
    sessions.delete(token);
    return { valid: false, reason: "session expired" };
  }
  const user = users.get(session.userId);
  if (!user) {
    sessions.delete(token);
    return { valid: false, reason: "user not found" };
  }
  if (user.status !== "ACTIVE") {
    sessions.delete(token);
    return { valid: false, reason: `user status is ${user.status}` };
  }
  if (user.licenseKey) {
    const validation = validateLicense(user.licenseKey);
    if (!validation.valid) {
      session.licenseValid = false;
      return { valid: false, reason: `license invalid: ${validation.reason}` };
    }
  }
  session.licenseValid = true;
  user.lastActivity = Date.now();
  return { valid: true, session };
}

export function revokeAccess(userId: string, reason: string): RevocationResult {
  if (!reason || reason.length < 5) {
    return { revoked: false, reason: "revocation reason must be at least 5 characters" };
  }
  const user = users.get(userId);
  if (!user) {
    return { revoked: false, reason: "user not found" };
  }
  if (user.status === "REVOKED" || user.status === "SUSPENDED") {
    return { revoked: false, reason: `user already in ${user.status} state` };
  }
  for (const [token, session] of sessions) {
    if (session.userId === userId) {
      sessions.delete(token);
    }
  }
  user.status = "REVOKED";
  user.suspendedAt = Date.now();
  user.metadata["revocationReason"] = reason;
  logAuditEvent({
    type: "permission_violation",
    severity: "high",
    source: "beta-user-manager",
    detail: `Beta user revoked: ${user.email} — reason: ${reason}`,
    metadata: { userId, reason },
  });
  return { revoked: true };
}

export function suspendBetaUser(userId: string, reason: string): RevocationResult {
  if (!reason || reason.length < 5) {
    return { revoked: false, reason: "suspension reason must be at least 5 characters" };
  }
  const user = users.get(userId);
  if (!user) {
    return { revoked: false, reason: "user not found" };
  }
  if (user.status === "REVOKED") {
    return { revoked: false, reason: "cannot suspend a revoked user" };
  }
  user.status = "SUSPENDED";
  user.suspendedAt = Date.now();
  user.metadata["suspensionReason"] = reason;
  for (const [token, session] of sessions) {
    if (session.userId === userId) {
      sessions.delete(token);
    }
  }
  logAuditEvent({
    type: "permission_violation",
    severity: "medium",
    source: "beta-user-manager",
    detail: `Beta user suspended: ${user.email} — reason: ${reason}`,
    metadata: { userId, reason },
  });
  return { revoked: true };
}

export function getBetaUser(userId: string): BetaUser | undefined {
  return users.get(userId);
}

export function listBetaUsers(status?: BetaStatus): BetaUser[] {
  const all = Array.from(users.values());
  if (status) {
    return all.filter((u) => u.status === status);
  }
  return all;
}

export function getActiveSessionCount(): number {
  const now = Date.now();
  let count = 0;
  for (const session of sessions.values()) {
    if (now <= session.expiresAt) {
      const user = users.get(session.userId);
      if (user && user.status === "ACTIVE") {
        count++;
      }
    }
  }
  return count;
}

export function clearAllBetaUsers(): void {
  users.clear();
  sessions.clear();
}
