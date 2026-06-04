import { describe, it, expect, beforeEach } from "vitest";
import {
  setupAlertRules,
  evaluateMetric,
  routeAlert,
  generateLaunchReport,
  acknowledgeAlert,
  getAlertHistory,
  clearAlertHistory,
} from "../../lib/monitoring/production-alerts";

describe("TestAlertRoutingAccuracy", () => {
  beforeEach(() => {
    clearAlertHistory();
  });

  it("should setup default alert rules with correct thresholds", () => {
    const rules = setupAlertRules();
    expect(rules).toHaveLength(5);
    const crashRule = rules.find((r) => r.name === "crash_rate_exceeded");
    expect(crashRule).toBeDefined();
    expect(crashRule!.threshold).toBe(0.01);
    expect(crashRule!.severity).toBe("critical");
    expect(crashRule!.channel).toBe("pagerduty");
  });

  it("should trigger alert when crash rate exceeds threshold", () => {
    setupAlertRules();
    const alerts = evaluateMetric("crash_rate", 0.02);
    expect(alerts).toHaveLength(1);
    expect(alerts[0].ruleName).toBe("crash_rate_exceeded");
    expect(alerts[0].severity).toBe("critical");
    expect(alerts[0].value).toBe(0.02);
  });

  it("should not trigger alert when metric is below threshold", () => {
    setupAlertRules();
    const alerts = evaluateMetric("crash_rate", 0.005);
    expect(alerts).toHaveLength(0);
  });

  it("should route alerts through all supported channels", () => {
    setupAlertRules();
    const alerts = evaluateMetric("unsigned_update", 1);
    expect(alerts).toHaveLength(1);
    expect(alerts[0].channel).toBe("pagerduty");
    const routed = routeAlert("email", alerts[0]);
    expect(routed).toBe(true);
    const routed2 = routeAlert("webhook", alerts[0]);
    expect(routed2).toBe(true);
    const routed3 = routeAlert("logstream", alerts[0]);
    expect(routed3).toBe(true);
  });

  it("should generate launch report with health status", () => {
    setupAlertRules();
    evaluateMetric("crash_rate", 0.005);
    const report = generateLaunchReport("1.0.0", 24, 150, 0.005, 150);
    expect(report.version).toBe("1.0.0");
    expect(report.uptimeHours).toBe(24);
    expect(report.activeUsers).toBe(150);
    expect(report.healthy).toBe(true);
    expect(report.totalAlerts).toBeGreaterThanOrEqual(0);
  });
});
