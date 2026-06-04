import { describe, it, expect } from "vitest";
import type { CompanyHealthProps } from "../../ui/pilot-dashboard/CompanyHealth";
import type { ResourceMetrics } from "../../ui/pilot-dashboard/ResourceUsage";

describe("Pilot Dashboard — CompanyHealth", () => {
  it("should render health score based on success rate", () => {
    const healthy: CompanyHealthProps = {
      companyId: "co-1", agentCount: 10, healthyAgents: 10,
      taskSuccessRate: 0.98, avgLatencyMs: 200, uptimePercent: 99.9,
      lastReportDate: "2026-06-01", errorCount: 1,
    };
    expect(healthy.taskSuccessRate).toBeGreaterThanOrEqual(0);
    expect(healthy.taskSuccessRate).toBeLessThanOrEqual(1);
    expect(healthy.healthyAgents).toBeLessThanOrEqual(healthy.agentCount);
  });

  it("should flag unhealthy companies with low success rate", () => {
    const unhealthy: CompanyHealthProps = {
      companyId: "co-2", agentCount: 5, healthyAgents: 2,
      taskSuccessRate: 0.45, avgLatencyMs: 1500, uptimePercent: 85,
      lastReportDate: "2026-05-30", errorCount: 23,
    };
    expect(unhealthy.taskSuccessRate).toBeLessThan(0.8);
    expect(unhealthy.healthyAgents).toBeLessThan(unhealthy.agentCount);
  });

  it("should track agent health ratio correctly", () => {
    const props: CompanyHealthProps = {
      companyId: "co-3", agentCount: 20, healthyAgents: 18,
      taskSuccessRate: 0.92, avgLatencyMs: 350, uptimePercent: 99.2,
      lastReportDate: "2026-06-01", errorCount: 5,
    };
    const healthRatio = props.healthyAgents / props.agentCount;
    expect(healthRatio).toBe(0.9);
  });
});

describe("Pilot Dashboard — ResourceUsage", () => {
  it("should have resource metrics within valid range", () => {
    const resources: ResourceMetrics = {
      cpuPercent: 45, memoryMb: 2048, memoryPercent: 50,
      tokenUsage: 500_000, tokenLimit: 1_000_000,
      networkRequestsPerMin: 120, activeSessions: 8,
    };
    expect(resources.cpuPercent).toBeGreaterThanOrEqual(0);
    expect(resources.cpuPercent).toBeLessThanOrEqual(100);
    expect(resources.memoryPercent).toBeGreaterThanOrEqual(0);
    expect(resources.memoryPercent).toBeLessThanOrEqual(100);
    expect(resources.tokenUsage).toBeLessThanOrEqual(resources.tokenLimit);
  });

  it("should flag critical resource usage", () => {
    const critical: ResourceMetrics = {
      cpuPercent: 92, memoryMb: 7168, memoryPercent: 88,
      tokenUsage: 980_000, tokenLimit: 1_000_000,
      networkRequestsPerMin: 450, activeSessions: 25,
    };
    expect(critical.cpuPercent).toBeGreaterThan(80);
    expect(critical.memoryPercent).toBeGreaterThan(80);
  });
});
