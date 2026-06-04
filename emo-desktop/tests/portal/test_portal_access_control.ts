import { describe, it, expect, beforeEach } from "vitest";
import {
  registerCompany,
  validateLicense,
  updateCompanyStatus,
  getAllCompanies,
  clearAllCompanies,
  getCompany,
} from "../../lib/portal/license-manager";
import { ingestReport, aggregateDailyMetrics, getReportCount, clearAllReports } from "../../lib/portal/metric-aggregator";

describe("Portal Access Control", () => {
  beforeEach(() => {
    clearAllCompanies();
    clearAllReports();
  });

  it("should block access for unregistered license keys", () => {
    const validation = validateLicense("NONEXISTENT-KEY");
    expect(validation.valid).toBe(false);
    expect(validation.reason).toBe("license key not found");
  });

  it("should block access for suspended companies", () => {
    const { company } = registerCompany("Blocked Corp", "BLOCKED-KEY-001");
    updateCompanyStatus(company.id, "suspended");

    const validation = validateLicense(company.licenseKey);
    expect(validation.valid).toBe(false);
    expect(validation.reason).toBe("license suspended");
  });

  it("should block access for expired licenses", () => {
    const { company } = registerCompany("Expired Co", "EXPIRED-KEY-001", { durationDays: -1 });
    const validation = validateLicense(company.licenseKey);
    expect(validation.valid).toBe(false);
    expect(validation.reason).toBe("license expired");
  });

  it("should allow access only for active companies", () => {
    const { company: c1 } = registerCompany("Active Co", "ACTIVE-KEY-001");
    const { company: c2 } = registerCompany("Suspended Co", "SUSPENDED-KEY-001");
    updateCompanyStatus(c2.id, "suspended");
    const { company: c3 } = registerCompany("Another Active", "ACTIVE-KEY-002");

    const allCompanies = getAllCompanies();
    const activeCount = allCompanies.filter((c) => c.status === "active").length;
    expect(activeCount).toBe(2);

    const validation1 = validateLicense(c1.licenseKey);
    expect(validation1.valid).toBe(true);

    const validation2 = validateLicense(c2.licenseKey);
    expect(validation2.valid).toBe(false);

    const validation3 = validateLicense(c3.licenseKey);
    expect(validation3.valid).toBe(true);
  });

  it("should reject companies with short license keys", () => {
    const result = registerCompany("Bad Key Co", "SHORT");
    expect(result.created).toBe(false);
    expect(result.reason).toBe("invalid license key");
  });
});
