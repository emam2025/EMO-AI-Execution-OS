import { describe, it, expect, beforeEach } from "vitest";
import {
  registerCompany,
  validateLicense,
  listActivePilots,
  updateCompanyStatus,
  clearAllCompanies,
} from "../../lib/portal/license-manager";
import {
  ingestReport,
  aggregateDailyMetrics,
  detectAnomalies,
  clearAllReports,
} from "../../lib/portal/metric-aggregator";
import { generateReport, verifyAuditTrail } from "../../lib/portal/compliance-reporter";
import type { AuditEntry } from "../../lib/safety/policy-engine";

describe("Portal Integration", () => {
  beforeEach(() => {
    clearAllCompanies();
    clearAllReports();
  });

  it("should register company then validate its license end-to-end", () => {
    const { company, created } = registerCompany("Enterprise Co", "ENT-KEY-2026", { maxAgents: 25 });
    expect(created).toBe(true);

    const validation = validateLicense(company.licenseKey);
    expect(validation.valid).toBe(true);
    expect(validation.remainingSeats).toBe(25);
    expect(validation.features).toContain("pilot");
  });

  it("should collect metrics and generate compliance report", () => {
    ingestReport({ companyId: "audit-corp", date: "2026-06-01", metrics: { cpu: 42, mem: 55, latency: 150 } });
    ingestReport({ companyId: "audit-corp", date: "2026-06-02", metrics: { cpu: 48, mem: 60, latency: 200 } });

    const metrics = aggregateDailyMetrics();
    expect(metrics.length).toBeGreaterThanOrEqual(3);

    const report = generateReport("SOC2", "auditor", "audit-corp", [], []);
    expect(report.summary.totalChecks).toBe(5);
    expect(report.verified).toBe(true);
  });

  it("should detect anomalies in integrated metric pipeline", () => {
    for (let i = 0; i < 8; i++) {
      ingestReport({ companyId: "c1", date: `2026-06-${String(i + 1).padStart(2, "0")}`, metrics: { error_rate: 2 + Math.random() * 3 } });
    }
    ingestReport({ companyId: "c1", date: "2026-06-15", metrics: { error_rate: 25 } });

    const anomalies = detectAnomalies(2);
    expect(anomalies.length).toBeGreaterThan(0);
  });

  it("should enforce core freeze — no imports from core or releases", () => {
    const fs = require("fs");
    const portalFiles = [
      "lib/portal/license-manager.ts",
      "lib/portal/metric-aggregator.ts",
      "lib/portal/compliance-reporter.ts",
      "ui/portal/CompanyRegistry.tsx",
      "ui/portal/MetricDashboard.tsx",
      "ui/portal/ComplianceExport.tsx",
      "ui/portal/FeedbackTriage.tsx",
      "tests/portal/test_license_management.ts",
      "tests/portal/test_metric_aggregation.ts",
      "tests/portal/test_compliance_reporting.ts",
      "tests/portal/test_portal_ui.tsx",
      "tests/portal/test_portal_integration.ts",
    ];

    for (const file of portalFiles) {
      const content = fs.readFileSync(file, "utf-8");
      const imports = content.match(/from\s+["']([^"']+)["']/g) || [];
      for (const imp of imports) {
        const path = imp.match(/["']([^"']+)["']/)![1];
        expect(path).not.toMatch(/^\.\.\/core\//);
        expect(path).not.toMatch(/^\.\.\/releases\//);
        expect(path).not.toMatch(/^\.\.\/\.\.\/core\//);
        expect(path).not.toMatch(/^\.\.\/\.\.\/releases\//);
        expect(path).not.toMatch(/^\//);
      }
    }
  });

  it("should verify audit trail integrity with various entry types", () => {
    const emptyResult = verifyAuditTrail([]);
    expect(emptyResult.valid).toBe(false);
    expect(emptyResult.issues).toContain("audit trail is empty");

    const validLog: AuditEntry[] = [
      { timestamp: 1000, action: "read", decision: "ALLOW", initiatedBy: "user1", reason: "permitted" },
      { timestamp: 2000, action: "write", decision: "ALLOW", initiatedBy: "user1", reason: "permitted" },
      { timestamp: 3000, action: "delete", decision: "DENY", initiatedBy: "user2", reason: "blocked" },
    ];
    const validResult = verifyAuditTrail(validLog);
    expect(validResult.valid).toBe(true);

    const invalidLog: AuditEntry[] = [
      { timestamp: 2000, action: "write", decision: "ALLOW", initiatedBy: "user1", reason: "ok" },
      { timestamp: 1000, action: "read", decision: "ALLOW", initiatedBy: "user1", reason: "ok" },
    ];
    const invalidResult = verifyAuditTrail(invalidLog);
    expect(invalidResult.valid).toBe(false);
    expect(invalidResult.issues.length).toBeGreaterThan(0);
  });
});
