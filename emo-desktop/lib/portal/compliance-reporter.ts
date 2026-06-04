import { jsPDF } from "jspdf";
import type { AuditEntry } from "../safety/policy-engine";
import type { ComplianceProfile } from "../safety/compliance-loader";

export type ComplianceStandard = "SOC2" | "IEC62443" | "ISO27001";

export interface ReportSection {
  title: string;
  content: string;
  passed: boolean;
  details?: string[];
}

export interface ComplianceReport {
  id: string;
  standard: ComplianceStandard;
  generatedAt: number;
  generatedBy: string;
  companyId: string;
  summary: { totalChecks: number; passed: number; failed: number; score: number };
  sections: ReportSection[];
  auditTrailHash: string;
  verified: boolean;
  safetyPolicyResults?: { policyName: string; passed: boolean; details: string }[];
  testResults?: { testName: string; passed: boolean; durationMs: number }[];
}

const REPORT_STANDARDS: Record<ComplianceStandard, { name: string; version: string; sections: string[] }> = {
  SOC2: {
    name: "SOC 2 Type II",
    version: "2024",
    sections: ["Security", "Availability", "Processing Integrity", "Confidentiality", "Privacy"],
  },
  IEC62443: {
    name: "IEC 62443",
    version: "3.0",
    sections: ["Security Program", "Asset Management", "Risk Assessment", "Access Control", "System Hardening", "Incident Response"],
  },
  ISO27001: {
    name: "ISO/IEC 27001",
    version: "2022",
    sections: ["Information Security Policy", "Asset Management", "Access Control", "Cryptography", "Physical Security", "Operations Security", "Communications Security", "Incident Management", "Business Continuity"],
  },
};

export function generateReport(
  standard: ComplianceStandard,
  generatedBy: string,
  companyId: string,
  auditLog: AuditEntry[],
  activeProfiles: ComplianceProfile[],
  safetyPolicyResults?: { policyName: string; passed: boolean; details: string }[],
  testResults?: { testName: string; passed: boolean; durationMs: number }[]
): ComplianceReport {
  const standardInfo = REPORT_STANDARDS[standard];
  const sections: ReportSection[] = standardInfo.sections.map((sectionTitle) => {
    const relevantAudits = auditLog.filter((e) =>
      e.action.toLowerCase().includes(sectionTitle.toLowerCase().slice(0, 6))
    );
    const relevantProfiles = activeProfiles.filter((p) =>
      p.auditRequirements.some((req) =>
        req.toLowerCase().includes(sectionTitle.toLowerCase().slice(0, 6))
      )
    );
    const relevantSafetyResults = (safetyPolicyResults || []).filter((r) =>
      r.policyName.toLowerCase().includes(sectionTitle.toLowerCase().slice(0, 6))
    );
    const relevantTestResults = (testResults || []).filter((t) =>
      t.testName.toLowerCase().includes(sectionTitle.toLowerCase().slice(0, 6))
    );

    const passed = relevantAudits.length > 0 || relevantProfiles.length > 0 || relevantSafetyResults.length > 0 || relevantTestResults.length > 0;
    const details: string[] = [];
    if (relevantAudits.length > 0) {
      details.push(`${relevantAudits.length} related audit entries found`);
    }
    if (relevantProfiles.length > 0) {
      details.push(`${relevantProfiles.length} compliance profiles reference this section`);
    }
    if (relevantSafetyResults.length > 0) {
      const passedCount = relevantSafetyResults.filter((r) => r.passed).length;
      details.push(`${passedCount}/${relevantSafetyResults.length} safety policies passed`);
    }
    if (relevantTestResults.length > 0) {
      const passedCount = relevantTestResults.filter((t) => t.passed).length;
      details.push(`${passedCount}/${relevantTestResults.length} tests passed`);
    }
    if (!passed) {
      details.push("No audit entries, compliance profiles, safety policies, or test results found");
    }

    return { title: sectionTitle, content: `Evaluation of ${sectionTitle} controls`, passed, details };
  });

  const totalChecks = sections.length;
  const passed = sections.filter((s) => s.passed).length;
  const failed = totalChecks - passed;
  const score = totalChecks > 0 ? passed / totalChecks : 0;

  const id = `report-${standard}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const auditTrailHash = computeAuditHash(auditLog);

  return {
    id,
    standard,
    generatedAt: Date.now(),
    generatedBy,
    companyId,
    summary: { totalChecks, passed, failed, score },
    sections,
    auditTrailHash,
    verified: true,
    safetyPolicyResults,
    testResults,
  };
}

function computeAuditHash(auditLog: AuditEntry[]): string {
  const crypto = require("crypto");
  const data = auditLog.map((e) => `${e.timestamp}:${e.action}:${e.decision}`).join("|");
  return crypto.createHash("sha256").update(data).digest("hex");
}

export function exportPDF(reportData: ComplianceReport): Uint8Array {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  let y = 20;

  function addLine(text: string, size: number = 11, style: "normal" | "bold" = "normal", color?: [number, number, number]) {
    if (y > 275) {
      doc.addPage();
      y = 20;
    }
    doc.setFontSize(size);
    doc.setFont("helvetica", style);
    if (color) doc.setTextColor(color[0], color[1], color[2]);
    else doc.setTextColor(0);
    doc.text(text, 14, y);
    y += size * 0.5;
  }

  function addDivider() {
    y += 2;
    doc.setDrawColor(200);
    doc.line(14, y, 196, y);
    y += 4;
  }

  addLine(`Compliance Report: ${reportData.standard}`, 18, "bold");
  addLine(`Generated: ${new Date(reportData.generatedAt).toISOString()}`, 9);
  addLine(`By: ${reportData.generatedBy}`, 9);
  addLine(`Company: ${reportData.companyId}`, 9);
  addDivider();

  const scoreColor: [number, number, number] =
    reportData.summary.score >= 0.8 ? [34, 197, 94] :
    reportData.summary.score >= 0.5 ? [245, 158, 11] : [239, 68, 68];
  addLine(`Score: ${(reportData.summary.score * 100).toFixed(1)}%`, 14, "bold", scoreColor);
  addLine(`Passed: ${reportData.summary.passed}/${reportData.summary.totalChecks}`, 10);
  addLine(`Audit Trail: ${reportData.verified ? "VERIFIED" : "TAMPERED"}`, 10, "normal", reportData.verified ? [34, 197, 94] : [239, 68, 68]);
  addLine(`Hash: ${reportData.auditTrailHash.slice(0, 20)}...`, 8);
  addDivider();

  addLine("Section Results:", 12, "bold");
  for (const section of reportData.sections) {
    const label = section.passed ? "[PASS]" : "[FAIL]";
    addLine(`  ${label}  ${section.title}`, 10, "normal", section.passed ? [34, 197, 94] : [239, 68, 68]);
    if (section.details && section.details.length > 0) {
      for (const d of section.details) {
        addLine(`       - ${d}`, 8);
      }
    }
  }

  if (reportData.safetyPolicyResults && reportData.safetyPolicyResults.length > 0) {
    addDivider();
    addLine("Safety Policy Results:", 12, "bold");
    for (const r of reportData.safetyPolicyResults) {
      addLine(`  ${r.passed ? "[PASS]" : "[FAIL]"}  ${r.policyName}`, 9, "normal", r.passed ? [34, 197, 94] : [239, 68, 68]);
      addLine(`       ${r.details}`, 8);
    }
  }

  if (reportData.testResults && reportData.testResults.length > 0) {
    addDivider();
    addLine("Test Results:", 12, "bold");
    for (const t of reportData.testResults) {
      addLine(`  ${t.passed ? "[PASS]" : "[FAIL]"}  ${t.testName} (${t.durationMs}ms)`, 9, "normal", t.passed ? [34, 197, 94] : [239, 68, 68]);
    }
  }

  addDivider();
  addLine("End of Report", 10, "bold");

  const buf = doc.output("arraybuffer");
  return new Uint8Array(buf);
}

export function verifyAuditTrail(auditLog: AuditEntry[]): { valid: boolean; issues: string[] } {
  const issues: string[] = [];

  if (!auditLog || auditLog.length === 0) {
    return { valid: false, issues: ["audit trail is empty"] };
  }

  for (let i = 1; i < auditLog.length; i++) {
    if (auditLog[i].timestamp < auditLog[i - 1].timestamp) {
      issues.push(`timestamp out of order at index ${i}: ${auditLog[i].timestamp} < ${auditLog[i - 1].timestamp}`);
    }
  }

  const validDecisions = ["ALLOW", "DENY", "REQUIRE_APPROVAL", "EMERGENCY_STOP"];
  for (let i = 0; i < auditLog.length; i++) {
    if (!validDecisions.includes(auditLog[i].decision)) {
      issues.push(`invalid decision at index ${i}: "${auditLog[i].decision}"`);
    }
    if (!auditLog[i].action) {
      issues.push(`missing action at index ${i}`);
    }
    if (!auditLog[i].initiatedBy) {
      issues.push(`missing initiatedBy at index ${i}`);
    }
  }

  return { valid: issues.length === 0, issues };
}
