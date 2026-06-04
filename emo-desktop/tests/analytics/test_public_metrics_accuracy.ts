import { describe, it, expect, beforeEach } from "vitest";
import {
  trackEvent,
  computeMetrics,
  exportAnalytics,
  clearAllEvents,
} from "../../lib/analytics/public-aggregator";

describe("TestMetricsPrivacyScrubbing", () => {
  beforeEach(() => {
    clearAllEvents();
  });

  it("should track events and compute DAU/WAU correctly", () => {
    trackEvent("app_launch", { version: "1.0.0" }, "session-a");
    trackEvent("task_start", { taskId: "t1" }, "session-a");
    trackEvent("task_complete", { taskId: "t1" }, "session-a");
    trackEvent("app_launch", {}, "session-b");
    trackEvent("task_start", { taskId: "t2" }, "session-b");
    trackEvent("task_fail", { taskId: "t2" }, "session-b");
    const now = Date.now();
    const metrics = computeMetrics({ start: now - 86400000, end: now + 1000 });
    expect(metrics.totalEvents).toBe(6);
    expect(metrics.totalSessions).toBe(2);
    expect(metrics.taskSuccessRate).toBe(0.5);
    expect(metrics.dau).toBeGreaterThanOrEqual(1);
  });

  it("should scrub PII from event properties (email, API keys)", () => {
    const event = trackEvent("feedback_submit", {
      message: "Great app!",
      email: "user@test.com",
      api_key: "sk-abc123",
    }, "session-pii");
    expect(event).not.toBeNull();
    expect(event!.properties).not.toHaveProperty("email");
    expect(event!.properties).not.toHaveProperty("api_key");
    expect(event!.properties).toHaveProperty("message");
    expect(event!.anonymized).toBe(true);
  });

  it("should compute crash rate correctly", () => {
    trackEvent("app_launch", {}, "s1");
    trackEvent("task_start", {}, "s1");
    trackEvent("crash_occurred", { error: "OOM" }, "s1");
    trackEvent("app_launch", {}, "s2");
    trackEvent("task_complete", {}, "s2");
    const now = Date.now();
    const metrics = computeMetrics({ start: now - 86400000, end: now + 1000 });
    expect(metrics.crashRate).toBeCloseTo(0.2, 1);
    expect(metrics.totalEvents).toBe(5);
  });

  it("should export analytics as JSON with anonymized flag", () => {
    trackEvent("app_launch", { version: "1.0.0" }, "s1");
    trackEvent("feature_view", { feature: "dashboard" }, "s1");
    const json = exportAnalytics("json");
    const report = JSON.parse(json);
    expect(report.anonymized).toBe(true);
    expect(report.metrics.totalEvents).toBe(2);
    expect(report.generatedAt).toBeGreaterThan(0);
  });

  it("should export analytics as CSV with correct columns", () => {
    trackEvent("app_launch", {}, "s1");
    trackEvent("task_complete", {}, "s1");
    const csv = exportAnalytics("csv");
    expect(csv).toContain("metric,value");
    expect(csv).toContain("dau,");
    expect(csv).toContain("task_success_rate,");
    expect(csv).toContain("event_name,count");
  });
});
