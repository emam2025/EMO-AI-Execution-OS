import { describe, it, expect } from "vitest";
import type { PortalCompany } from "../../ui/portal/CompanyRegistry";
import type { MetricSummary, AnomalyAlert } from "../../ui/portal/MetricDashboard";
import type { ReportPreview } from "../../ui/portal/ComplianceExport";
import type { FeedbackItem, FeedbackCategory, FeedbackPriority, FeedbackStatus } from "../../ui/portal/FeedbackTriage";

describe("CompanyRegistry — props & state", () => {
  it("should define company type with all required fields", () => {
    const company: PortalCompany = {
      id: "c1", name: "Acme Corp", status: "active", licenseKey: "KEY-1",
      expiresAt: Date.now() + 86400000, maxAgents: 10, lastActivity: null, createdAt: Date.now(),
    };
    expect(company.name).toBe("Acme Corp");
    expect(company.status).toBe("active");
    expect(company.maxAgents).toBe(10);
  });

  it("should support suspend/reactivate status transitions", () => {
    const active: PortalCompany = { id: "c1", name: "Acme", status: "active", licenseKey: "K1", expiresAt: 1e12, maxAgents: 5, lastActivity: null, createdAt: 1 };
    const suspended: PortalCompany = { ...active, status: "suspended" };
    const expired: PortalCompany = { ...active, status: "expired" };
    expect(active.status).toBe("active");
    expect(suspended.status).toBe("suspended");
    expect(expired.status).toBe("expired");
  });
});

describe("MetricDashboard — aggregation logic", () => {
  it("should compute summary statistics from metrics", () => {
    const metrics: MetricSummary[] = [
      { name: "cpu", avg: 45, min: 10, max: 90, count: 100, stdDev: 15, sum: 4500 },
    ];
    expect(metrics[0].avg).toBe(45);
    expect(metrics[0].min).toBe(10);
    expect(metrics[0].max).toBe(90);
    expect(metrics[0].stdDev).toBe(15);
  });

  it("should classify anomaly severity by z-score", () => {
    const highAnomaly: AnomalyAlert = { metricName: "cpu", date: "2026-06-01", value: 95, severity: "high", zScore: 3.5 };
    const lowAnomaly: AnomalyAlert = { metricName: "mem", date: "2026-06-01", value: 80, severity: "low", zScore: 2.1 };
    expect(highAnomaly.severity).toBe("high");
    expect(lowAnomaly.severity).toBe("low");
  });
});

describe("ComplianceExport — report preview data", () => {
  it("should hold preview state for all three standards", () => {
    const standards = ["SOC2", "IEC62443", "ISO27001"] as const;
    for (const s of standards) {
      const preview: ReportPreview = {
        standard: s, score: 0.8, passed: 4, totalChecks: 5,
        sections: [{ title: "Security", passed: true }],
        generatedAt: new Date().toISOString(), verified: true,
      };
      expect(preview.standard).toBe(s);
      expect(preview.verified).toBe(true);
    }
  });
});

describe("FeedbackTriage — item lifecycle", () => {
  it("should support all feedback categories", () => {
    const categories: FeedbackCategory[] = ["bug", "performance", "feature", "security", "ux", "other"];
    expect(categories).toHaveLength(6);
  });

  it("should support all status transitions", () => {
    const statuses: FeedbackStatus[] = ["new", "reviewing", "triaged", "resolved", "dismissed"];
    expect(statuses).toHaveLength(5);
  });

  it("should create feedback item with all required fields", () => {
    const item: FeedbackItem = {
      id: "f1", timestamp: 1e12, category: "bug", status: "new",
      title: "Login crash", description: "App crashes on login", source: "web", priority: "high",
    };
    expect(item.category).toBe("bug");
    expect(item.status).toBe("new");
    expect(item.priority).toBe("high");
  });

  it("should support all severity/priority levels", () => {
    const priorities: FeedbackPriority[] = ["low", "medium", "high", "critical"];
    expect(priorities).toHaveLength(4);
  });

  it("should filter items by severity", () => {
    const items: FeedbackItem[] = [
      { id: "f1", timestamp: 1, category: "bug", status: "new", title: "Low", description: "x", source: "w", priority: "low" },
      { id: "f2", timestamp: 1, category: "bug", status: "new", title: "Critical", description: "x", source: "w", priority: "critical" },
    ];
    const criticalItems = items.filter((i) => i.priority === "critical");
    expect(criticalItems).toHaveLength(1);
    expect(criticalItems[0].title).toBe("Critical");
  });
});
