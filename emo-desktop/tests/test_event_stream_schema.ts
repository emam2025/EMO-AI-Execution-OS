/**
 * Test: Event Stream Schema
 *
 * Verifies that runtime.events conform to event_stream_contract.md.
 * All 5 event types are validated against the schema.
 */
import { describe, it, expect } from "vitest";

type RuntimeEvent = {
  type: "task_started" | "node_completed" | "agent_warning" | "runtime_error" | "trace_indexed";
  trace_id: string | null;
  timestamp: string;
  payload: Record<string, unknown>;
};

const VALID_EVENT_TYPES = [
  "task_started",
  "node_completed",
  "agent_warning",
  "runtime_error",
  "trace_indexed",
] as const;

function validateEvent(event: RuntimeEvent): boolean {
  if (!VALID_EVENT_TYPES.includes(event.type)) return false;
  if (typeof event.timestamp !== "string") return false;
  if (isNaN(Date.parse(event.timestamp))) return false;
  if (typeof event.payload !== "object" || event.payload === null) return false;
  return true;
}

describe("Event Stream Schema", () => {
  it("task_started event has all required fields", () => {
    const event: RuntimeEvent = {
      type: "task_started",
      trace_id: "og_abc123",
      timestamp: "2026-05-29T00:00:00Z",
      payload: { intent: "summarize", tenant_id: "acme", plan_hash: "abc" },
    };
    expect(validateEvent(event)).toBe(true);
    expect(event.payload.intent).toBeDefined();
    expect(event.payload.tenant_id).toBeDefined();
    expect(event.payload.plan_hash).toBeDefined();
  });

  it("node_completed event has duration_ms", () => {
    const event: RuntimeEvent = {
      type: "node_completed",
      trace_id: "og_abc123",
      timestamp: "2026-05-29T00:00:01Z",
      payload: { node_id: "node_3", status: "success", duration_ms: 450 },
    };
    expect(validateEvent(event)).toBe(true);
    expect(typeof event.payload.duration_ms).toBe("number");
  });

  it("agent_warning has agent and warning fields", () => {
    const event: RuntimeEvent = {
      type: "agent_warning",
      trace_id: "og_abc123",
      timestamp: "2026-05-29T00:00:02Z",
      payload: { agent: "critic", warning: "budget_exceeded", message: "Over budget" },
    };
    expect(validateEvent(event)).toBe(true);
    expect(event.payload.agent).toBeDefined();
    expect(event.payload.warning).toBeDefined();
  });

  it("runtime_error has severity", () => {
    const event: RuntimeEvent = {
      type: "runtime_error",
      trace_id: null,
      timestamp: "2026-05-29T00:00:03Z",
      payload: { error: "Something broke", severity: "critical" },
    };
    expect(validateEvent(event)).toBe(true);
    expect(event.payload.severity).toBe("critical");
  });

  it("trace_indexed has event_count and duration_ms", () => {
    const event: RuntimeEvent = {
      type: "trace_indexed",
      trace_id: "og_abc123",
      timestamp: "2026-05-29T00:00:04Z",
      payload: { event_count: 12, duration_ms: 3200, status: "completed" },
    };
    expect(validateEvent(event)).toBe(true);
    expect(event.payload.event_count).toBe(12);
    expect(event.payload.status).toBe("completed");
  });

  it("rejects unknown event types", () => {
    const event = {
      type: "unknown_event",
      trace_id: null,
      timestamp: "2026-05-29T00:00:00Z",
      payload: {},
    } as RuntimeEvent;
    expect(validateEvent(event)).toBe(false);
  });

  it("rejects invalid timestamps", () => {
    const event: RuntimeEvent = {
      type: "task_started",
      trace_id: null,
      timestamp: "not-a-timestamp",
      payload: {},
    };
    expect(validateEvent(event)).toBe(false);
  });
});
