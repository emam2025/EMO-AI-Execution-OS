import { describe, it, expect, beforeEach } from "vitest";
import { applyIndustrialLevel, getAuditLog, clearAuditLog } from "../../lib/safety/policy-engine";
import {
  loadComplianceProfile, applyProfile, getLoadedProfileIds,
  clearProfileCache, validateProfileCompatibility, type ComplianceProfile,
} from "../../lib/safety/compliance-loader";

describe("Compliance Profiles", () => {
  beforeEach(() => {
    clearAuditLog();
    clearProfileCache();
  });

  it("should load iso27001 profile with level 2", async () => {
    const profile = await loadComplianceProfile("iso27001");
    expect(profile.id).toBe("iso27001");
    expect(profile.industrialLevel).toBe(2);
    expect(profile.standard).toBe("ISO/IEC 27001");
  });

  it("should load soc2 profile", async () => {
    const profile = await loadComplianceProfile("soc2");
    expect(profile.id).toBe("soc2");
    expect(profile.industrialLevel).toBe(2);
  });

  it("should load nist profile with level 3", async () => {
    const profile = await loadComplianceProfile("nist");
    expect(profile.id).toBe("nist");
    expect(profile.industrialLevel).toBe(3);
  });

  it("should load iec62443 profile", async () => {
    const profile = await loadComplianceProfile("iec62443");
    expect(profile.id).toBe("iec62443");
    expect(profile.industrialLevel).toBe(3);
  });

  it("should load isa95 profile", async () => {
    const profile = await loadComplianceProfile("isa95");
    expect(profile.id).toBe("isa95");
    expect(profile.industrialLevel).toBe(2);
  });

  it("should load iec61511 profile with level 4", async () => {
    const profile = await loadComplianceProfile("iec61511");
    expect(profile.id).toBe("iec61511");
    expect(profile.industrialLevel).toBe(4);
  });

  it("should throw for unknown profile", async () => {
    await expect(loadComplianceProfile("unknown_standard")).rejects.toThrow();
  });

  it("should apply profile to policy engine", async () => {
    const profile = await loadComplianceProfile("nist");
    const config = applyProfile(profile);
    expect(config.industrialLevel).toBe(3);
    expect(config.approvalPolicy.dualApproval).toBe(true);
    expect(config.auditRequirements.tamperProof).toBe(true);
  });

  it("should detect level conflicts between profiles", () => {
    const profiles: ComplianceProfile[] = [
      { id: "a", name: "A", standard: "S1", version: "1", industrialLevel: 2, overrides: {}, auditRequirements: [], dataRetentionPolicy: { maxDays: 365, autoPurge: false, encryptAtRest: true } },
      { id: "b", name: "B", standard: "S2", version: "1", industrialLevel: 2, overrides: {}, auditRequirements: [], dataRetentionPolicy: { maxDays: 365, autoPurge: false, encryptAtRest: true } },
      { id: "c", name: "C", standard: "S3", version: "1", industrialLevel: 3, overrides: {}, auditRequirements: [], dataRetentionPolicy: { maxDays: 365, autoPurge: false, encryptAtRest: true } },
    ];
    const result = validateProfileCompatibility(profiles);
    expect(result.compatible).toBe(false);
    expect(result.conflicts.length).toBeGreaterThan(0);
  });
});
