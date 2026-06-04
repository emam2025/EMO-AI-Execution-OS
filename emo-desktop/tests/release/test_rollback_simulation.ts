import { describe, it, expect, beforeEach } from "vitest";
import {
  configureRollbackPlan,
  checkFailureThresholds,
  executeRollback,
  simulateRollback,
  getRollbackPlan,
  resetRollbackState,
} from "../../lib/distribution/rollback-executor";
import { setChannel, gradualRollout, clearAllChannels } from "../../lib/distribution/release-channels";

describe("TestRollbackExecutionTime", () => {
  beforeEach(() => {
    resetRollbackState();
    clearAllChannels();
  });

  it("should execute rollback within 5 minutes (<300000ms)", () => {
    setChannel("stable", "1.0.0");
    setChannel("stable", "1.1.0");
    setChannel("beta", "1.2.0-beta");
    gradualRollout("beta", 100);
    const start = performance.now();
    const exec = executeRollback(["stable"]);
    const elapsed = performance.now() - start;
    expect(elapsed).toBeLessThan(300000);
    expect(exec.success).toBe(true);
    expect(exec.durationMs).toBeLessThan(300000);
    expect(exec.channelsReverted).toContain("stable");
  });

  it("should detect failure thresholds and trigger rollback", () => {
    const result = checkFailureThresholds([
      { metric: "crash_rate", value: 0.02 },
      { metric: "avg_latency_ms", value: 500 },
    ]);
    expect(result.shouldRollback).toBe(true);
    expect(result.triggered).toHaveLength(1);
    expect(result.triggered[0]).toContain("crash_rate");
  });

  it("should not trigger rollback when metrics are within thresholds", () => {
    const result = checkFailureThresholds([
      { metric: "crash_rate", value: 0.005 },
      { metric: "avg_latency_ms", value: 150 },
    ]);
    expect(result.shouldRollback).toBe(false);
    expect(result.triggered).toHaveLength(0);
  });

  it("should simulate rollback and restore original state", () => {
    setChannel("stable", "1.0.0");
    setChannel("stable", "1.1.0");
    const exec = simulateRollback(["stable"]);
    expect(exec.success).toBe(true);
  });

  it("should configure custom rollback plan with thresholds", () => {
    const plan = configureRollbackPlan({
      failureThresholds: [
        { metric: "error_rate", threshold: 0.1, operator: "gt" },
      ],
      autoExecute: false,
    });
    expect(plan.failureThresholds).toHaveLength(1);
    expect(plan.autoExecute).toBe(false);
    const retrieved = getRollbackPlan();
    expect(retrieved.id).toBe("emergency-rollback-v1");
  });
});
