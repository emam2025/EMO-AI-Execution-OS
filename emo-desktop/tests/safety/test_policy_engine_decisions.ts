import { describe, it, expect, beforeEach } from "vitest";
import {
  evaluateAction, applyIndustrialLevel, emergencyStop, releaseEmergencyStop,
  getAuditLog, clearAuditLog, type Action, type PolicyContext,
} from "../../lib/safety/policy-engine";

function makeContext(overrides?: Partial<PolicyContext>): PolicyContext {
  return {
    industrialLevel: 1,
    activeCompliance: [],
    userRoles: ["operator"],
    approvedBy: [],
    emergencyOverride: false,
    auditTrail: [],
    ...overrides,
  };
}

function makeAction(overrides?: Partial<Action>): Action {
  return {
    id: "test-action-1",
    category: "read",
    description: "Test action",
    target: "system:test",
    initiatedBy: "test-operator",
    timestamp: Date.now(),
    ...overrides,
  };
}

describe("Policy Engine — Level 1 (Business)", () => {
  beforeEach(() => clearAuditLog());

  it("should ALLOW read actions at level 1 without approval", () => {
    const result = evaluateAction(makeAction({ category: "read" }), makeContext({ industrialLevel: 1 }));
    expect(result.decision).toBe("ALLOW");
  });

  it("should REQUIRE_APPROVAL for deploy at level 1", () => {
    const result = evaluateAction(makeAction({ category: "deploy" }), makeContext({ industrialLevel: 1 }));
    expect(result.decision).toBe("REQUIRE_APPROVAL");
  });

  it("should DENY system_shutdown at level 1", () => {
    const result = evaluateAction(makeAction({ category: "system_shutdown" }), makeContext({ industrialLevel: 1 }));
    expect(result.decision).toBe("DENY");
  });
});

describe("Policy Engine — Level 2 (Operational)", () => {
  beforeEach(() => clearAuditLog());

  it("should REQUIRE_APPROVAL for config_change at level 2", () => {
    const result = evaluateAction(makeAction({ category: "config_change" }), makeContext({ industrialLevel: 2 }));
    expect(result.decision).toBe("REQUIRE_APPROVAL");
  });

  it("should DENY privilege_escalation at level 2", () => {
    const result = evaluateAction(makeAction({ category: "privilege_escalation" }), makeContext({ industrialLevel: 2 }));
    expect(result.decision).toBe("DENY");
  });
});

describe("Policy Engine — Level 3 (Industrial)", () => {
  beforeEach(() => clearAuditLog());

  it("should REQUIRE_DUAL_APPROVAL for deploy at level 3", () => {
    const result = evaluateAction(makeAction({ category: "deploy" }), makeContext({ industrialLevel: 3 }));
    expect(result.decision).toBe("REQUIRE_APPROVAL");
  });

  it("should ALLOW deploy at level 3 with dual approval", () => {
    const result = evaluateAction(
      makeAction({ category: "deploy" }),
      makeContext({ industrialLevel: 3, approvedBy: ["alice", "bob"] }),
    );
    expect(result.decision).toBe("ALLOW");
  });
});

describe("Policy Engine — Level 4 (Critical Infrastructure)", () => {
  beforeEach(() => clearAuditLog());

  it("should DENY delete at level 4", () => {
    const result = evaluateAction(makeAction({ category: "delete" }), makeContext({ industrialLevel: 4 }));
    expect(result.decision).toBe("DENY");
  });

  it("should REQUIRE_DUAL_APPROVAL for data_export at level 4", () => {
    const result = evaluateAction(makeAction({ category: "data_export" }), makeContext({ industrialLevel: 4 }));
    expect(result.decision).toBe("REQUIRE_APPROVAL");
  });
});

describe("Policy Engine — Emergency Stop", () => {
  beforeEach(() => clearAuditLog());

  it("should return EMERGENCY_STOP when emergency override is active", () => {
    const ctx = makeContext({ emergencyOverride: true });
    const result = evaluateAction(makeAction({ category: "read" }), ctx);
    expect(result.decision).toBe("EMERGENCY_STOP");
  });

  it("should record emergency stop in audit trail", () => {
    const ctx = makeContext();
    emergencyStop(ctx, "test-operator", "Safety drill");
    const log = getAuditLog();
    expect(log.some((e) => e.decision === "EMERGENCY_STOP")).toBe(true);
  });

  it("should resume normal operations after release", () => {
    const ctx = makeContext();
    emergencyStop(ctx, "test-operator", "Safety drill");
    releaseEmergencyStop(ctx, "test-operator");
    const result = evaluateAction(makeAction({ category: "read" }), ctx);
    expect(result.decision).toBe("ALLOW");
  });
});
