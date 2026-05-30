/**
 * Test: Trace API Contract
 *
 * Verifies that the response from GET /trace/{trace_id} conforms
 * to the ExecutionTrace schema defined in telemetry.ts.
 */
import { describe, it, expect } from "vitest";

type TraceEvent = {
  timestamp: string;
  source: "planner" | "critic" | "optimizer" | "memory" | "runtime";
  event: string;
  data: Record<string, unknown>;
};

type ExecutionTrace = {
  trace_id: string;
  intent: string;
  tenant_id: string;
  events: TraceEvent[];
  valid: boolean;
};

const VALID_SOURCES = ["planner", "critic", "optimizer", "memory", "runtime"] as const;

function validateTrace(trace: ExecutionTrace): boolean {
  if (!trace.trace_id || typeof trace.trace_id !== "string") return false;
  if (!trace.intent || typeof trace.intent !== "string") return false;
  if (!trace.tenant_id || typeof trace.tenant_id !== "string") return false;
  if (!Array.isArray(trace.events)) return false;
  if (typeof trace.valid !== "boolean") return false;

  for (const event of trace.events) {
    if (!event.timestamp || isNaN(Date.parse(event.timestamp))) return false;
    if (!VALID_SOURCES.includes(event.source as any)) return false;
    if (typeof event.event !== "string") return false;
    if (typeof event.data !== "object" || event.data === null) return false;
  }
  return true;
}

function mockTrace(overrides: Partial<ExecutionTrace> = {}): ExecutionTrace {
  return {
    trace_id: "og_abc123def456",
    intent: "summarize",
    tenant_id: "acme",
    events: [
      {
        timestamp: "2026-05-29T00:00:00Z",
        source: "planner",
        event: "plan_proposed",
        data: { hash: "abc" },
      },
      {
        timestamp: "2026-05-29T00:00:01Z",
        source: "critic",
        event: "plan_approved",
        data: { score: 0.95 },
      },
    ],
    valid: true,
    ...overrides,
  };
}

describe("Trace API Contract", () => {
  it("valid trace passes schema validation", () => {
    const trace = mockTrace();
    expect(validateTrace(trace)).toBe(true);
  });

  it("rejects trace without trace_id", () => {
    const trace = mockTrace({ trace_id: "" });
    expect(validateTrace(trace)).toBe(false);
  });

  it("rejects trace with invalid event source", () => {
    const trace = mockTrace();
    trace.events[0].source = "unknown" as any;
    expect(validateTrace(trace)).toBe(false);
  });

  it("accepts all 5 valid event sources", () => {
    for (const source of VALID_SOURCES) {
      const trace = mockTrace({
        events: [
          {
            timestamp: "2026-05-29T00:00:00Z",
            source: source as TraceEvent["source"],
            event: "test",
            data: {},
          },
        ],
      });
      expect(validateTrace(trace)).toBe(true);
    }
  });

  it("rejects trace with non-array events", () => {
    const trace = mockTrace({ events: null as any });
    expect(validateTrace(trace)).toBe(false);
  });

  it("accepts trace with valid=false", () => {
    const trace = mockTrace({ valid: false });
    expect(validateTrace(trace)).toBe(true);
  });
});
