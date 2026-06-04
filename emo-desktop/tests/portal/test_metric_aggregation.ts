import { describe, it, expect, beforeEach } from "vitest";
import {
  ingestReport,
  aggregateDailyMetrics,
  getTrendView,
  detectAnomalies,
  clearAllReports,
  getReportCount,
  ingestEncryptedReport,
} from "../../lib/portal/metric-aggregator";
import { encryptReport } from "../../lib/pilot/pilot-mode-manager";

describe("Metric Aggregation", () => {
  beforeEach(() => {
    clearAllReports();
  });

  it("should aggregate metrics across multiple reports", () => {
    ingestReport({ companyId: "c1", date: "2026-06-01", metrics: { cpu: 45, mem: 60 } });
    ingestReport({ companyId: "c1", date: "2026-06-01", metrics: { cpu: 55, mem: 70 } });

    const aggregated = aggregateDailyMetrics();
    const cpu = aggregated.find((m) => m.name === "cpu");
    expect(cpu).toBeDefined();
    expect(cpu!.avg).toBe(50);
    expect(cpu!.count).toBe(2);
    expect(cpu!.min).toBe(45);
    expect(cpu!.max).toBe(55);
  });

  it("should filter by company ID", () => {
    ingestReport({ companyId: "c1", date: "2026-06-01", metrics: { cpu: 50 } });
    ingestReport({ companyId: "c2", date: "2026-06-01", metrics: { cpu: 80 } });

    const filtered = aggregateDailyMetrics("c1");
    expect(filtered).toHaveLength(1);
    expect(filtered[0].avg).toBe(50);
  });

  it("should return trend view over time", () => {
    ingestReport({ companyId: "c1", date: "2026-06-01", metrics: { latency: 100 } });
    ingestReport({ companyId: "c1", date: "2026-06-02", metrics: { latency: 120 } });
    ingestReport({ companyId: "c1", date: "2026-06-03", metrics: { latency: 80 } });

    const trend = getTrendView("latency");
    expect(trend).toHaveLength(3);
    expect(trend[0].value).toBe(100);
    expect(trend[1].value).toBe(120);
    expect(trend[2].value).toBe(80);
  });

  it("should detect anomalies above threshold", () => {
    for (let i = 0; i < 10; i++) {
      ingestReport({ companyId: "c1", date: `2026-06-${String(i + 1).padStart(2, "0")}`, metrics: { cpu: 50 + Math.random() * 10 } });
    }
    ingestReport({ companyId: "c1", date: "2026-06-20", metrics: { cpu: 95 } });

    const anomalies = detectAnomalies(2);
    expect(anomalies.length).toBeGreaterThan(0);
    expect(anomalies[0].metricName).toBe("cpu");
    expect(anomalies[0].zScore).toBeGreaterThan(2);
  });

  it("should not leak company IDs in aggregated output", () => {
    ingestReport({ companyId: "secret-company-xyz", date: "2026-06-01", metrics: { cpu: 50 } });
    ingestReport({ companyId: "secret-company-xyz", date: "2026-06-02", metrics: { cpu: 60 } });

    const aggregated = aggregateDailyMetrics();
    for (const m of aggregated) {
      expect(m.name).not.toContain("secret");
    }
  });

  it("should decrypt and ingest P6 encrypted reports", () => {
    const plainReport = JSON.stringify({
      companyId: "p6-company",
      date: "2026-06-15",
      metrics: { cpu: 75, mem: 80 },
    });
    const encrypted = encryptReport(plainReport);
    expect(encrypted).toContain(":");

    const result = ingestEncryptedReport(encrypted);
    expect(result).toBe(true);
    expect(getReportCount()).toBe(1);

    const aggregated = aggregateDailyMetrics();
    const cpu = aggregated.find((m) => m.name === "cpu");
    expect(cpu).toBeDefined();
    expect(cpu!.avg).toBe(75);
  });
});
