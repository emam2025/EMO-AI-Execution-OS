import { describe, it, expect } from "vitest";
import { generateReport, exportPDF, verifyAuditTrail } from "../../lib/portal/compliance-reporter";
import type { AuditEntry } from "../../lib/safety/policy-engine";
import type { ComplianceProfile } from "../../lib/safety/compliance-loader";

function makeAuditEntry(overrides: Partial<AuditEntry> = {}): AuditEntry {
  return {
    timestamp: Date.now(),
    action: "test_action",
    decision: "ALLOW",
    initiatedBy: "test_user",
    reason: "test",
    ...overrides,
  };
}

function makeProfile(overrides: Partial<ComplianceProfile> = {}): ComplianceProfile {
  return {
    id: "test-profile",
    name: "Test Profile",
    standard: "ISO27001",
    version: "2022",
    industrialLevel: 2,
    overrides: {},
    auditRequirements: ["access control", "security"],
    dataRetentionPolicy: { maxDays: 365, autoPurge: false, encryptAtRest: true },
    ...overrides,
  };
}

describe("Compliance Reporting", () => {
  it("should generate SOC2 report with correct structure", () => {
    const report = generateReport("SOC2", "admin", "company-a", [], []);
    expect(report.standard).toBe("SOC2");
    expect(report.summary.totalChecks).toBe(5);
    expect(report.summary.passed + report.summary.failed).toBe(5);
    expect(report.verified).toBe(true);
    expect(report.id).toContain("report-SOC2");
  });

  it("should generate IEC62443 report with 6 sections", () => {
    const report = generateReport("IEC62443", "admin", "company-b", [], []);
    expect(report.standard).toBe("IEC62443");
    expect(report.summary.totalChecks).toBe(6);
    expect(report.sections).toHaveLength(6);
  });

  it("should generate ISO27001 report with 9 sections", () => {
    const report = generateReport("ISO27001", "admin", "company-c", [], []);
    expect(report.standard).toBe("ISO27001");
    expect(report.summary.totalChecks).toBe(9);
    expect(report.sections).toHaveLength(9);
  });

  it("should pass sections with relevant audit entries and profiles", () => {
    const auditLog: AuditEntry[] = [
      makeAuditEntry({ action: "access_control_check", decision: "ALLOW" }),
      makeAuditEntry({ action: "security_audit", decision: "ALLOW" }),
    ];
    const profiles: ComplianceProfile[] = [
      makeProfile({ auditRequirements: ["access control", "security"] }),
    ];

    const report = generateReport("SOC2", "admin", "company-d", auditLog, profiles);
    expect(report.summary.passed).toBeGreaterThan(0);
  });

  it("should generate real PDF with jsPDF (binary Uint8Array)", () => {
    const report = generateReport("SOC2", "tester", "company-e", [], []);
    const pdf = exportPDF(report);
    expect(pdf).toBeInstanceOf(Uint8Array);
    expect(pdf.length).toBeGreaterThan(100);
    const header = new TextDecoder().decode(pdf.slice(0, 8));
    expect(header.startsWith("%PDF-")).toBe(true);
  });

  it("should include safety policy and test results in report", () => {
    const safetyResults = [
      { policyName: "access_control_policy", passed: true, details: "All checks passed" },
      { policyName: "encryption_policy", passed: false, details: "AES-256 not enforced" },
    ];
    const testResults = [
      { testName: "login_test", passed: true, durationMs: 120 },
      { testName: "audit_test", passed: false, durationMs: 45 },
    ];

    const report = generateReport("ISO27001", "auditor", "company-f", [], [], safetyResults, testResults);
    expect(report.safetyPolicyResults).toHaveLength(2);
    expect(report.testResults).toHaveLength(2);

    const hasAccessControl = report.sections.some((s) =>
      s.title.toLowerCase().includes("access") && s.passed === true
    );
    expect(hasAccessControl).toBe(true);
  });
});
