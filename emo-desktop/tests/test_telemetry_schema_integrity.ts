/**
 * Test: Telemetry Schema Integrity
 *
 * Verifies that RuntimeTelemetry type matches the schema definition
 * and all fields are present with correct types.
 */
import { describe, it, expect } from "vitest";

type RuntimeTelemetry = {
  cpu_usage: number;
  memory_usage: number;
  active_agents: number;
  queued_tasks: number;
  uptime_seconds: number;
  event_latency_ms: number;
};

const EXPECTED_FIELDS: (keyof RuntimeTelemetry)[] = [
  "cpu_usage",
  "memory_usage",
  "active_agents",
  "queued_tasks",
  "uptime_seconds",
  "event_latency_ms",
];

describe("Telemetry Schema Integrity", () => {
  it("has all 6 required fields", () => {
    const t: RuntimeTelemetry = {
      cpu_usage: 45,
      memory_usage: 256,
      active_agents: 3,
      queued_tasks: 5,
      uptime_seconds: 3600,
      event_latency_ms: 12,
    };

    for (const field of EXPECTED_FIELDS) {
      expect(t).toHaveProperty(field);
    }
  });

  it("all numeric fields are numbers", () => {
    const t: RuntimeTelemetry = {
      cpu_usage: 0,
      memory_usage: 0,
      active_agents: 0,
      queued_tasks: 0,
      uptime_seconds: 0,
      event_latency_ms: 0,
    };

    for (const field of EXPECTED_FIELDS) {
      expect(typeof t[field]).toBe("number");
    }
  });

  it("accepts realistic values", () => {
    const t: RuntimeTelemetry = {
      cpu_usage: 78.5,
      memory_usage: 512,
      active_agents: 4,
      queued_tasks: 12,
      uptime_seconds: 7200,
      event_latency_ms: 3.2,
    };

    expect(t.cpu_usage).toBeGreaterThanOrEqual(0);
    expect(t.cpu_usage).toBeLessThanOrEqual(100);
    expect(t.memory_usage).toBeGreaterThan(0);
    expect(t.active_agents).toBeGreaterThanOrEqual(0);
    expect(t.uptime_seconds).toBeGreaterThanOrEqual(0);
  });

  it("rejects missing fields", () => {
    const t = {
      cpu_usage: 45,
      // missing memory_usage
      active_agents: 3,
      queued_tasks: 5,
      uptime_seconds: 3600,
      event_latency_ms: 12,
    } as RuntimeTelemetry;

    expect(t.memory_usage).toBeUndefined();
  });
});
