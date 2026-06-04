import { describe, it, expect, beforeEach } from "vitest";
import {
  registerBetaUser,
  activateBetaUser,
  issueBetaSession,
  validateBetaSession,
  revokeAccess,
  suspendBetaUser,
  getBetaUser,
  getActiveSessionCount,
  clearAllBetaUsers,
} from "../../lib/beta/beta-user-manager";

describe("TestBetaLifecycleSecurity", () => {
  beforeEach(() => {
    clearAllBetaUsers();
  });

  it("should register a beta user with PENDING status", () => {
    const result = registerBetaUser("tester@example.com", "TestCorp", "tester");
    expect(result.created).toBe(true);
    expect(result.user).not.toBeNull();
    expect(result.user!.status).toBe("PENDING");
    expect(result.user!.email).toBe("tester@example.com");
    expect(result.user!.company).toBe("TestCorp");
    expect(result.user!.role).toBe("tester");
  });

  it("should reject duplicate email registration", () => {
    registerBetaUser("dup@example.com", "CorpA", "tester");
    const dup = registerBetaUser("dup@example.com", "CorpB", "admin");
    expect(dup.created).toBe(false);
    expect(dup.reason).toBe("email already registered");
  });

  it("should activate PENDING user and issue valid session", () => {
    const { user } = registerBetaUser("active@test.com", "ActiveCo", "admin");
    expect(user!.status).toBe("PENDING");
    const activated = activateBetaUser(user!.id);
    expect(activated.user!.status).toBe("ACTIVE");
    const session = issueBetaSession(user!.id);
    expect(session).not.toBeNull();
    expect(session!.token).toMatch(/^bet_/);
    const validation = validateBetaSession(session!.token);
    expect(validation.valid).toBe(true);
    expect(validation.session!.role).toBe("admin");
  });

  it("should revoke access and invalidate all sessions", () => {
    const { user } = registerBetaUser("revoke@test.com", "RevokeCo", "tester");
    activateBetaUser(user!.id);
    const session = issueBetaSession(user!.id);
    expect(session).not.toBeNull();
    const revocation = revokeAccess(user!.id, "policy violation detected");
    expect(revocation.revoked).toBe(true);
    const fetched = getBetaUser(user!.id);
    expect(fetched!.status).toBe("REVOKED");
    const validation = validateBetaSession(session!.token);
    expect(validation.valid).toBe(false);
    expect(validation.reason).toMatch(/(session not found|user status)/);
  });

  it("should suspend and reactivate user lifecycle", () => {
    const { user } = registerBetaUser("cycle@test.com", "CycleCo", "viewer");
    activateBetaUser(user!.id);
    const session1 = issueBetaSession(user!.id);
    expect(session1).not.toBeNull();
    const suspension = suspendBetaUser(user!.id, "temporary compliance review");
    expect(suspension.revoked).toBe(true);
    const fetched = getBetaUser(user!.id);
    expect(fetched!.status).toBe("SUSPENDED");
    const sessionAfter = issueBetaSession(user!.id);
    expect(sessionAfter).toBeNull();
    const activeCount = getActiveSessionCount();
    expect(activeCount).toBe(0);
  });
});
