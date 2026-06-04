import { describe, it, expect, beforeEach } from "vitest";
import {
  evaluateAction, applyIndustrialLevel, emergencyStop, getAuditLog, clearAuditLog,
  type Action, type PolicyContext,
} from "../../lib/safety/policy-engine";
import { calculateRiskScores } from "../../lib/safety/risk-calculator";

function makeContext(overrides?: Partial<PolicyContext>): PolicyContext {
  return { industrialLevel: 1, activeCompliance: [], userRoles: ["operator"], approvedBy: [], emergencyOverride: false, auditTrail: [], ...overrides };
}

function makeAction(overrides?: Partial<Action>): Action {
  return { id: "int-test", category: "read", description: "Integration test", target: "system:test", initiatedBy: "test", timestamp: Date.now(), ...overrides };
}

describe("Safety Integration — Full Flow", () => {
  beforeEach(() => clearAuditLog());

  it("should detect risk → enforce policy → log decision", () => {
    const action = makeAction({ category: "privilege_escalation", description: "Escalate privileges" });
    const ctx = makeContext({ industrialLevel: 3 });
    const config = applyIndustrialLevel(3);
    const riskProfile = calculateRiskScores(action, config);
    const result = evaluateAction(action, ctx);

    expect(riskProfile.riskScore).toBeGreaterThan(0.5);
    expect(result.decision).toBe("DENY");
    const log = getAuditLog();
    expect(log.some((e) => e.action === "int-test" && e.decision === "DENY")).toBe(true);
  });

  it("should escalate from detection to emergency stop for critical threats", () => {
    const action = makeAction({ category: "system_shutdown", description: "Unauthorized shutdown attempt" });
    const ctx = makeContext({ industrialLevel: 4 });

    const result1 = evaluateAction(action, ctx);
    expect(result1.decision).toBe("DENY");

    const config = applyIndustrialLevel(4);
    const risk = calculateRiskScores(action, config);
    expect(risk.riskScore).toBeGreaterThanOrEqual(0.7);

    emergencyStop(ctx, "auto-guard", `High risk action blocked: ${action.description}`);
    const result2 = evaluateAction(action, ctx);
    expect(result2.decision).toBe("EMERGENCY_STOP");

    const log = getAuditLog();
    expect(log.length).toBeGreaterThanOrEqual(3);
  });

  it("should apply level 4 IEC 61511 limits to all actions", () => {
    const config = applyIndustrialLevel(4);
    expect(config.resourceLimits.maxCpuPercent).toBeLessThanOrEqual(25);
    expect(config.resourceLimits.maxMemoryMb).toBeLessThanOrEqual(1024);
    expect(config.resourceLimits.maxNetworkRequestsPerMin).toBeLessThanOrEqual(30);
    expect(config.approvalPolicy.dualApproval).toBe(true);
    expect(config.auditRequirements.tamperProof).toBe(true);
  });

  it("should produce risk scores within valid range", () => {
    const categories: Array<Action["category"]> = ["read", "write", "execute", "deploy", "delete", "config_change", "network_access", "privilege_escalation", "data_export", "system_shutdown"];
    for (const level of [1, 2, 3, 4] as const) {
      const config = applyIndustrialLevel(level);
      for (const category of categories) {
        const risk = calculateRiskScores(makeAction({ category }), config);
        expect(risk.riskScore).toBeGreaterThanOrEqual(0);
        expect(risk.riskScore).toBeLessThanOrEqual(1);
        expect(risk.impactScore).toBeGreaterThanOrEqual(0);
        expect(risk.impactScore).toBeLessThanOrEqual(1);
        expect(risk.confidenceScore).toBeGreaterThanOrEqual(0);
        expect(risk.confidenceScore).toBeLessThanOrEqual(1);
      }
    }
  });

  it("should complete full detection-to-recovery flow", () => {
    const ctx = makeContext({ industrialLevel: 3, approvedBy: [] });

    const action = makeAction({ category: "deploy", description: "Deploy untrusted update" });
    const result = evaluateAction(action, ctx);
    expect(result.decision).toBe("REQUIRE_APPROVAL");

    const riskProfile = result.riskProfile!;
    expect(riskProfile.riskScore).toBeGreaterThan(0);

    ctx.approvedBy = ["admin-1", "admin-2"];
    const result2 = evaluateAction(action, ctx);
    expect(result2.decision).toBe("ALLOW");

    const log = getAuditLog();
    expect(log.length).toBe(2);

    const first = log[0];
    expect(first.decision).toBe("REQUIRE_APPROVAL");
    expect(first.riskProfile).toBeDefined();
  });
});
