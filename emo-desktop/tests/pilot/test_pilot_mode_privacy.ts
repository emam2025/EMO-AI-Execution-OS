import { describe, it, expect, beforeEach } from "vitest";
import {
  enablePilotMode, disablePilotMode, isPilotModeEnabled, getActiveCompanyId,
  trackMetric, getMetricsBuffer, clearMetricsBuffer,
  encryptReport, getAggregatedMetrics,
} from "../../lib/pilot/pilot-mode-manager";

describe("Pilot Mode — Privacy & Security", () => {
  beforeEach(() => {
    disablePilotMode();
    clearMetricsBuffer();
  });

  it("should not track metrics before pilot mode is enabled", () => {
    const result = trackMetric("task_success", 0.95);
    expect(result).toBe(false);
    expect(getMetricsBuffer().length).toBe(0);
  });

  it("should anonymize company ID in tracked metrics", () => {
    enablePilotMode("acme-corp-123");
    trackMetric("task_success", 0.95);
    const metrics = getMetricsBuffer();
    expect(metrics.length).toBe(1);
    expect(metrics[0].tags["company_id"]).not.toBe("acme-corp-123");
    expect(metrics[0].tags["company_id"]).toMatch(/^[a-f0-9]{16}$/);
    expect(metrics[0].anonymized).toBe(true);
  });

  it("should reject sensitive keys in metric tags", () => {
    enablePilotMode("test-co");
    const result = trackMetric("api_call", 200, {
      api_key: "sk-test123",
      email: "user@test.com",
      endpoint: "/v1/chat",
      status: "ok",
    });
    expect(result).toBe(true);
    const metrics = getMetricsBuffer();
    expect(metrics[0].tags["api_key"]).toBeUndefined();
    expect(metrics[0].tags["email"]).toBeUndefined();
    expect(metrics[0].tags["endpoint"]).toBe("v1chat");
    expect(metrics[0].tags["status"]).toBe("ok");
  });

  it("should encrypt reports with AES-256-CBC", () => {
    const plaintext = JSON.stringify({ companyId: "test", metrics: [1, 2, 3] });
    const encrypted = encryptReport(plaintext);
    expect(encrypted).not.toBe(plaintext);
    expect(encrypted).toContain(":");
    const [iv, ciphertext] = encrypted.split(":");
    expect(iv.length).toBe(32);
    expect(ciphertext.length).toBeGreaterThan(0);
  });

  it("should not include raw company ID in aggregated metrics", () => {
    enablePilotMode("secret-company-name");
    trackMetric("uptime", 99.5);
    trackMetric("latency", 150);
    const aggregated = getAggregatedMetrics();
    for (const m of aggregated) {
      expect(m.companyId).not.toBe("secret-company-name");
      expect(m.companyId).toMatch(/^[a-f0-9]{16}$/);
    }
  });
});
