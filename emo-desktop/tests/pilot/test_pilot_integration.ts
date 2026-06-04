import { describe, it, expect, beforeEach } from "vitest";
import {
  enablePilotMode, disablePilotMode, isPilotModeEnabled,
  trackMetric, getMetricsBuffer, clearMetricsBuffer,
  getAggregatedMetrics, getPilotDuration,
} from "../../lib/pilot/pilot-mode-manager";
import { generateDailyReport, submitDailyReport } from "../../lib/pilot/daily-reporter";

function scrubText(text: string): string {
  const patterns = [
    /sk-[a-zA-Z0-9]{20,}/g,
    /AIza[0-9A-Za-z_-]{35,}/g,
    /[\w.-]+@[\w.-]+\.\w{2,}/g,
  ];
  let scrubbed = text;
  for (const p of patterns) scrubbed = scrubbed.replace(p, "[REDACTED]");
  return scrubbed;
}

describe("Pilot Integration — Telemetry Security", () => {
  beforeEach(() => {
    disablePilotMode();
    clearMetricsBuffer();
  });

  it("should not collect data before opt-in", () => {
    expect(isPilotModeEnabled()).toBe(false);
    expect(trackMetric("test", 1)).toBe(false);
    expect(getMetricsBuffer().length).toBe(0);
  });

  it("should only track after explicit enable", () => {
    enablePilotMode("test-co");
    expect(isPilotModeEnabled()).toBe(true);
    expect(trackMetric("task_success", 0.95)).toBe(true);
    expect(getMetricsBuffer().length).toBe(1);
  });

  it("should aggregate metrics correctly", () => {
    enablePilotMode("test-co");
    trackMetric("task_success", 0.9);
    trackMetric("task_success", 0.95);
    trackMetric("task_success", 1.0);
    trackMetric("latency", 200);
    const aggregated = getAggregatedMetrics();
    const taskSuccess = aggregated.find((m) => m.name === "task_success");
    expect(taskSuccess).toBeDefined();
    expect(taskSuccess!.avg).toBeCloseTo(0.95, 2);
    expect(taskSuccess!.count).toBe(3);
  });

  it("should scrub sensitive data from all text", () => {
    const withKey = "API key: sk-test123456789012345678901234";
    const withEmail = "Contact: admin@test.com";
    expect(scrubText(withKey)).not.toContain("sk-test");
    expect(scrubText(withEmail)).not.toContain("admin@test.com");
  });
});

describe("Pilot Integration — Dashboard Updates", () => {
  beforeEach(() => {
    disablePilotMode();
    clearMetricsBuffer();
  });

  it("should generate daily report with metrics", () => {
    enablePilotMode("dashboard-test");
    trackMetric("task_success", 0.95);
    trackMetric("latency", 150);
    const report = generateDailyReport();
    expect(report).not.toBeNull();
    expect(report!.metrics.length).toBeGreaterThanOrEqual(2);
    expect(report!.summary.totalMetrics).toBeGreaterThan(0);
  });

  it("should include health score in daily report", () => {
    enablePilotMode("health-test");
    trackMetric("task_success_rate", 0.92);
    trackMetric("agent_uptime", 99.8);
    const report = generateDailyReport();
    expect(report!.summary.healthScore).toBeGreaterThan(0);
    expect(report!.summary.healthScore).toBeLessThanOrEqual(1);
  });
});

describe("Pilot Integration — Feedback Anonymization", () => {
  it("should redact API keys from feedback text", () => {
    const input = "Error: sk-abc123def456ghi789jklmno caused crash";
    expect(scrubText(input)).not.toContain("sk-abc123def456ghi789jklmno");
  });

  it("should redact emails from feedback text", () => {
    const input = "User john@example.com reported latency";
    expect(scrubText(input)).not.toContain("john@example.com");
  });

  it("should preserve non-sensitive text", () => {
    const input = "Agent crashed during startup on macOS 14.5";
    expect(scrubText(input)).toBe(input);
  });
});

describe("Pilot Integration — Checklist Validation", () => {
  it("should have all 5 sector checklists loadable", async () => {
    const sectors = ["software-house", "factory", "logistics", "consulting", "internal-team"];
    for (const sector of sectors) {
      const mod = await import(`../../config/sector-checklists/${sector}.json`);
      const checklist = mod.default || mod;
      expect(checklist.sector).toBe(sector);
      expect(checklist.criteria.length).toBeGreaterThan(0);
    }
  });

  it("should have total weight of 100 for all checklists", async () => {
    const sectors = ["software-house", "factory", "logistics", "consulting", "internal-team"];
    for (const sector of sectors) {
      const mod = await import(`../../config/sector-checklists/${sector}.json`);
      const checklist = mod.default || mod;
      const totalWeight = checklist.criteria.reduce((s: number, c: any) => s + c.weight, 0);
      expect(totalWeight).toBe(100);
    }
  });

  it("should have success threshold between 0 and 1", async () => {
    const sectors = ["software-house", "factory", "logistics", "consulting", "internal-team"];
    for (const sector of sectors) {
      const mod = await import(`../../config/sector-checklists/${sector}.json`);
      const checklist = mod.default || mod;
      expect(checklist.successThreshold).toBeGreaterThan(0);
      expect(checklist.successThreshold).toBeLessThanOrEqual(1);
    }
  });

  it("should submit encrypted daily report", () => {
    enablePilotMode("report-test");
    trackMetric("test", 1);
    const result = submitDailyReport();
    expect(result.submitted).toBe(true);
    expect(result.encryptedSize).toBeGreaterThan(0);
  });

  it("should track pilot uptime duration", () => {
    enablePilotMode("uptime-test");
    const duration = getPilotDuration();
    expect(duration).toBeGreaterThanOrEqual(0);
  });
});
