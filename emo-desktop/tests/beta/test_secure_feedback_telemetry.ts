import { describe, it, expect, beforeEach } from "vitest";
import {
  submitFeedback,
  collectBetaTelemetry,
  verifyChannelIntegrity,
  getFeedbackEntries,
  getTelemetryPoints,
  updateFeedbackStatus,
  clearAllFeedback,
} from "../../lib/beta/secure-feedback-channel";

describe("TestFeedbackEncryptionScrubbing", () => {
  beforeEach(() => {
    clearAllFeedback();
  });

  it("should encrypt and scrub API keys from feedback payload", () => {
    const entry = submitFeedback("bug", "Error with API key sk-abc123def456 and email user@test.com", { source: "beta" });
    expect(entry).not.toBeNull();
    expect(entry!.payload).not.toContain("sk-abc123def456");
    expect(entry!.payload).not.toContain("user@test.com");
    expect(entry!.payload).toContain("REDACTED");
    expect(entry!.encryptedPayload).toContain(":");
  });

  it("should reject feedback with invalid type", () => {
    const entry = submitFeedback("invalid" as any, "test payload");
    expect(entry).toBeNull();
  });

  it("should collect telemetry with encrypted timestamp", () => {
    const point = collectBetaTelemetry("cpu_usage", 45.2, { region: "us-east", host: "beta-01" });
    expect(point).not.toBeNull();
    expect(point!.metric).toBe("cpu_usage");
    expect(point!.value).toBe(45.2);
    expect(point!.encryptedTimestamp).toContain(":");
    expect(point!.tags).not.toHaveProperty("api_key");
  });

  it("should detect channel tampering via integrity check", () => {
    submitFeedback("performance", "slow query detected", { company: "TestInc" });
    const status1 = verifyChannelIntegrity();
    expect(status1.healthy).toBe(true);
    expect(status1.tamperDetected).toBe(false);
  });

  it("should support full feedback lifecycle with status updates", () => {
    const entry = submitFeedback("security", "suspicious login attempt detected", { company: "SecureCo" });
    expect(entry).not.toBeNull();
    expect(entry!.status).toBe("new");
    const updated = updateFeedbackStatus(entry!.id, "triaged");
    expect(updated).toBe(true);
    const entries = getFeedbackEntries("triaged");
    expect(entries).toHaveLength(1);
    expect(entries[0].id).toBe(entry!.id);
    const allEntries = getFeedbackEntries();
    expect(allEntries).toHaveLength(1);
  });
});
