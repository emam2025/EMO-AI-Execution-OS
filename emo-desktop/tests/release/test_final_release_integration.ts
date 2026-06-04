import { describe, it, expect, beforeEach } from "vitest";
import * as fs from "fs";
import * as path from "path";

import { setChannel, gradualRollout, clearAllChannels } from "../../lib/distribution/release-channels";
import { promoteToStable, verifyBackwardCompatibility, pullBetaChannel } from "../../lib/distribution/release-promoter";
import { setupAlertRules, evaluateMetric, generateLaunchReport, clearAlertHistory } from "../../lib/monitoring/production-alerts";
import { configureRollbackPlan, checkFailureThresholds, executeRollback } from "../../lib/distribution/rollback-executor";

describe("TestFinalReleaseIntegration", () => {
  beforeEach(() => {
    clearAllChannels();
    clearAlertHistory();
  });

  it("should complete full promotion → monitoring → rollback lifecycle", () => {
    setChannel("beta", "1.1.0-beta");
    gradualRollout("beta", 100);
    setChannel("stable", "1.0.0");
    const promotion = promoteToStable("1.1.0", 25);
    expect(promotion.success).toBe(true);
    setupAlertRules();
    const alerts = evaluateMetric("crash_rate", 0.02);
    expect(alerts).toHaveLength(1);
    setChannel("stable", "1.0.0");
    setChannel("stable", "1.1.0");
    const rollback = executeRollback(["stable"]);
    expect(rollback.success).toBe(true);
  });

  it("should verify launch readiness checklist file exists and is complete", () => {
    const checklistPath = path.resolve(__dirname, "../../config/launch-readiness-checklist.json");
    expect(fs.existsSync(checklistPath)).toBe(true);
    const content = JSON.parse(fs.readFileSync(checklistPath, "utf8"));
    expect(content.version).toBe("1.0.0");
    expect(content.gates).toHaveLength(12);
    expect(content.summary.totalGates).toBe(12);
    expect(content.summary.ready).toBe(true);
  });

  it("should have zero core imports in all P10 modules", () => {
    const p10Files = [
      "lib/distribution/release-promoter.ts",
      "lib/distribution/rollback-executor.ts",
      "lib/monitoring/production-alerts.ts",
    ];
    for (const file of p10Files) {
      const content = fs.readFileSync(file, "utf8");
      expect(content).not.toMatch(/from\s+["'](\.\.\/)*core\//);
      expect(content).not.toMatch(/from\s+["'](\.\.)*\/releases\//);
    }
  });

  it("should verify P10 certificate artifacts exist", () => {
    const certPath = path.resolve(__dirname, "../../../artifacts/product/P10_PRODUCTION_LAUNCH_CERTIFICATE.json");
    expect(fs.existsSync(certPath)).toBe(true);
  });

  it("should generate healthy launch report after simulation", () => {
    setupAlertRules();
    evaluateMetric("crash_rate", 0.003);
    evaluateMetric("avg_latency_ms", 200);
    const report = generateLaunchReport("1.0.0", 48, 500, 0.003, 200);
    expect(report.healthy).toBe(true);
    expect(report.uptimeHours).toBe(48);
    expect(report.activeUsers).toBe(500);
  });
});
