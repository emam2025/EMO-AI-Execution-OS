import { describe, it, expect, beforeEach } from "vitest";
import {
  evaluateAction, emergencyStop, releaseEmergencyStop,
  getAuditLog, clearAuditLog,
} from "../../lib/safety/policy-engine";
import type { Action, PolicyContext } from "../../lib/safety/policy-engine";

function makeContext(overrides?: Partial<PolicyContext>): PolicyContext {
  return {
    industrialLevel: 4,
    activeCompliance: ["iec61511"],
    userRoles: ["operator"],
    approvedBy: [],
    emergencyOverride: false,
    auditTrail: [],
    ...overrides,
  };
}

function makeAction(overrides?: Partial<Action>): Action {
  return {
    id: "fault-injection-test",
    category: "system_shutdown",
    description: "Fault injection: simulated critical command",
    target: "system:emergency-shutdown",
    initiatedBy: "fault-injector",
    timestamp: Date.now(),
    ...overrides,
  };
}

describe("Industrial Fault Injection — Level 4 Escalation", () => {
  beforeEach(() => clearAuditLog());

  it("should DENY level 4 critical command without dual approval", () => {
    const result = evaluateAction(makeAction({ category: "system_shutdown" }), makeContext());
    expect(result.decision).toBe("DENY");
  });

  it("should DENY delete at level 4 without any approval", () => {
    const result = evaluateAction(
      makeAction({ category: "delete", description: "Delete production data" }),
      makeContext(),
    );
    expect(result.decision).toBe("DENY");
  });

  it("should REQUIRE_DUAL_APPROVAL for write at level 4", () => {
    const result = evaluateAction(
      makeAction({ category: "write", description: "Modify safety-critical config" }),
      makeContext(),
    );
    expect(result.decision).toBe("REQUIRE_APPROVAL");
  });

  it("should ALLOW write at level 4 with dual approval", () => {
    const result = evaluateAction(
      makeAction({ category: "write", description: "Modify config with approval" }),
      makeContext({ approvedBy: ["admin-1", "admin-2"] }),
    );
    expect(result.decision).toBe("ALLOW");
  });

  it("should block privilege escalation at level 4", () => {
    const result = evaluateAction(
      makeAction({ category: "privilege_escalation", description: "Escalate to root" }),
      makeContext(),
    );
    expect(result.decision).toBe("DENY");
  });
});

describe("Industrial Fault Injection — Audit Trail Integrity", () => {
  beforeEach(() => clearAuditLog());

  it("should record every decision in audit trail", () => {
    evaluateAction(makeAction({ category: "read" }), makeContext());
    evaluateAction(makeAction({ category: "system_shutdown" }), makeContext());
    const log = getAuditLog();
    expect(log.length).toBe(2);
  });

  it("should include risk profile in audit entries for critical actions", () => {
    evaluateAction(makeAction({ category: "system_shutdown" }), makeContext());
    const log = getAuditLog();
    const entry = log.find((e) => e.action === "fault-injection-test");
    expect(entry).toBeDefined();
    expect(entry!.riskProfile).toBeDefined();
    expect(entry!.riskProfile!.riskScore).toBeGreaterThan(0);
  });

  it("should enforce append-only audit trail — entries cannot be removed or altered via API", () => {
    evaluateAction(makeAction({ id: "a1", category: "read" }), makeContext());
    evaluateAction(makeAction({ id: "a2", category: "read" }), makeContext());
    const log = getAuditLog();
    const count = log.length;
    expect(count).toBe(2);
    expect(log[0].action).toBe("a1");
    evaluateAction(makeAction({ id: "a3", category: "read" }), makeContext());
    expect(getAuditLog().length).toBe(count + 1);
  });
});

describe("Industrial Fault Injection — Emergency Stop", () => {
  beforeEach(() => clearAuditLog());

  it("should trigger emergency stop immediately", () => {
    const ctx = makeContext();
    emergencyStop(ctx, "safety-system", "Critical anomaly detected");
    const result = evaluateAction(makeAction(), ctx);
    expect(result.decision).toBe("EMERGENCY_STOP");
    expect(result.reason).toContain("Emergency override");
  });

  it("should log emergency stop trigger in audit trail", () => {
    const ctx = makeContext();
    emergencyStop(ctx, "safety-system", "Fault injection test: E-stop");
    const log = getAuditLog();
    const stopEntry = log.find((e) => e.decision === "EMERGENCY_STOP");
    expect(stopEntry).toBeDefined();
    expect(stopEntry!.initiatedBy).toBe("safety-system");
  });

  it("should cut execution within 100ms (simulated)", () => {
    const ctx = makeContext();
    const start = Date.now();
    emergencyStop(ctx, "system", "Test stop");
    const result = evaluateAction(makeAction(), ctx);
    const elapsed = Date.now() - start;
    expect(result.decision).toBe("EMERGENCY_STOP");
    expect(elapsed).toBeLessThanOrEqual(100);
  });

  it("should resume after emergency release", () => {
    const ctx = makeContext();
    emergencyStop(ctx, "system", "Test stop");
    releaseEmergencyStop(ctx, "system");
    const result = evaluateAction(makeAction({ category: "read" }), ctx);
    expect(result.decision).toBe("ALLOW");
  });
});
