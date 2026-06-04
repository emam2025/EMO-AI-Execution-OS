import { describe, it, expect, beforeEach } from "vitest";
import {
  registerCompany,
  validateLicense,
  listActivePilots,
  getAllCompanies,
  updateCompanyStatus,
  getCompanyCounts,
  clearAllCompanies,
  recordActivity,
} from "../../lib/portal/license-manager";

describe("License Management", () => {
  beforeEach(() => {
    clearAllCompanies();
  });

  it("should register a new company with valid license key", () => {
    const result = registerCompany("Acme Corp", "LIC-ABCD-1234-5678");
    expect(result.created).toBe(true);
    expect(result.company.name).toBe("Acme Corp");
    expect(result.company.status).toBe("active");
    expect(result.company.expiresAt).toBeGreaterThan(Date.now());
  });

  it("should reject duplicate company names", () => {
    registerCompany("Acme Corp", "LIC-ABCD-1234-5678");
    const result = registerCompany("Acme Corp", "LIC-XXXX-9999-0000");
    expect(result.created).toBe(false);
    expect(result.reason).toBe("company name already registered");
  });

  it("should validate active license keys", () => {
    const { company } = registerCompany("Beta Inc", "BETA-KEY-9999");
    const validation = validateLicense(company.licenseKey);
    expect(validation.valid).toBe(true);
    expect(validation.features).toContain("pilot");
    expect(validation.remainingSeats).toBeDefined();
  });

  it("should reject unknown license keys", () => {
    const validation = validateLicense("FAKE-KEY-0000");
    expect(validation.valid).toBe(false);
    expect(validation.reason).toBe("license key not found");
  });

  it("should reject suspended license keys", () => {
    const { company } = registerCompany("Gamma LLC", "GAMMA-KEY-123");
    updateCompanyStatus(company.id, "suspended");
    const validation = validateLicense(company.licenseKey);
    expect(validation.valid).toBe(false);
    expect(validation.reason).toBe("license suspended");
  });
});
