import { describe, it, expect, beforeEach } from "vitest";
import {
  promoteToStable,
  verifyBackwardCompatibility,
  pullBetaChannel,
  getRecommendedRolloutStep,
} from "../../lib/distribution/release-promoter";
import { setChannel, gradualRollout, clearAllChannels } from "../../lib/distribution/release-channels";

describe("TestStablePromotionIntegrity", () => {
  beforeEach(() => {
    clearAllChannels();
  });

  it("should promote beta version to stable with phased rollout", () => {
    setChannel("stable", "1.0.0");
    setChannel("beta", "1.1.0-beta");
    gradualRollout("beta", 100);
    const result = promoteToStable("1.1.0", 25);
    expect(result.success).toBe(true);
    expect(result.version).toBe("1.1.0");
    expect(result.rolloutPercentage).toBe(25);
    expect(result.backwardCompatible).toBe(true);
  });

  it("should reject promotion when beta channel not configured", () => {
    const result = promoteToStable("2.0.0", 25);
    expect(result.success).toBe(false);
    expect(result.reason).toContain("beta channel not configured");
  });

  it("should verify backward compatibility with valid config", () => {
    setChannel("stable", "1.0.0");
    const report = verifyBackwardCompatibility();
    expect(report.compatible).toBe(true);
    expect(report.checks.length).toBeGreaterThan(0);
    expect(report.checks.every((c) => c.passed)).toBe(true);
  });

  it("should pull beta channel and return migration count", () => {
    setChannel("beta", "1.1.0-beta");
    gradualRollout("beta", 100);
    setChannel("stable", "1.0.0");
    const result = pullBetaChannel();
    expect(result.migrated).toBe(0);
  });

  it("should recommend next rollout step incrementally", () => {
    expect(getRecommendedRolloutStep(0)).toBe(25);
    expect(getRecommendedRolloutStep(25)).toBe(50);
    expect(getRecommendedRolloutStep(50)).toBe(75);
    expect(getRecommendedRolloutStep(100)).toBe(100);
  });
});
