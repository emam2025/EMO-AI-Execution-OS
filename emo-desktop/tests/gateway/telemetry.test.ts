/**
 * Test: TelemetryAggregator — Cost, Latency & Failover Accuracy
 *
 * Verifies:
 *   - cost_per_token matches raw events (≥95% accuracy)
 *   - avg_latency_ms matches raw events (≥95% accuracy)
 *   - failover_count increments correctly
 *   - provider_success_rate computed correctly
 *   - total_requests / failed_requests tracking
 *   - Snapshot emission via callback
 *   - Reset clears all counters
 *   - Start/stop interval lifecycle
 *   - Destroy cleans up all resources
 *   - Empty aggregator returns defaults
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  TelemetryAggregator,
  type RawTelemetryEvent,
} from "../../lib/gateway/telemetry_aggregator";

describe("TelemetryAggregator — accuracy", () => {
  let agg: TelemetryAggregator;

  beforeEach(() => {
    agg = new TelemetryAggregator();
  });

  afterEach(() => {
    agg.destroy();
  });

  function makeEvent(
    overrides?: Partial<RawTelemetryEvent["payload"]>,
    eventType?: string,
  ): RawTelemetryEvent {
    return {
      type: eventType ?? "gateway_request",
      timestamp: new Date().toISOString(),
      payload: {
        provider_id: "openai",
        cost_per_token: 0.002,
        tokens_used: 100,
        latency_ms: 150,
        status_code: 200,
        failover: false,
        ...overrides,
      },
    };
  }

  it("cost_per_token matches raw event cost (≥95% accuracy)", () => {
    agg.ingest(makeEvent({ cost_per_token: 0.002, tokens_used: 100 }));
    agg.ingest(makeEvent({ cost_per_token: 0.003, tokens_used: 200 }));
    const snapshot = agg.getSnapshot();
    // Total cost = 0.002*100 + 0.003*200 = 0.2 + 0.6 = 0.8
    // Average = 0.4
    expect(snapshot.cost_per_token).toBeCloseTo(0.4, 3);
    expect(snapshot.cost_per_token).toBeGreaterThan(0);
  });

  it("avg_latency_ms matches raw event avg (≥95% accuracy)", () => {
    agg.ingest(makeEvent({ latency_ms: 100 }));
    agg.ingest(makeEvent({ latency_ms: 200 }));
    agg.ingest(makeEvent({ latency_ms: 300 }));
    const snapshot = agg.getSnapshot();
    expect(snapshot.avg_latency_ms).toBe(200);
  });

  it("failover_count increments on failover events", () => {
    agg.ingest(makeEvent({ failover: true }));
    agg.ingest(makeEvent({ failover: true }));
    agg.ingest(makeEvent({ failover: false }));
    const snapshot = agg.getSnapshot();
    expect(snapshot.failover_count).toBe(2);
  });

  it("provider_success_rate computes correctly", () => {
    agg.ingest(makeEvent({ status_code: 200 }));
    agg.ingest(makeEvent({ status_code: 200 }));
    agg.ingest(makeEvent({ status_code: 500 }));
    agg.ingest(makeEvent({ status_code: 200 }));
    const snapshot = agg.getSnapshot();
    expect(snapshot.total_requests).toBe(4);
    expect(snapshot.failed_requests).toBe(1);
    expect(snapshot.provider_success_rate).toBe(75);
  });

  it("total_session_cost accumulates across events", () => {
    agg.ingest(makeEvent({ cost_per_token: 0.001, tokens_used: 500 }));
    agg.ingest(makeEvent({ cost_per_token: 0.002, tokens_used: 300 }));
    // 0.001*500 + 0.002*300 = 0.5 + 0.6 = 1.1
    const snapshot = agg.getSnapshot();
    expect(snapshot.total_session_cost).toBeCloseTo(1.1, 3);
  });

  it("ingest without cost/tokens does not affect costs", () => {
    agg.ingest({ type: "gateway_health", timestamp: "", payload: { provider_id: "openai" } });
    const snapshot = agg.getSnapshot();
    expect(snapshot.total_session_cost).toBe(0);
    expect(snapshot.total_requests).toBe(1);
    expect(snapshot.failed_requests).toBe(0);
  });

  it("empty aggregator returns default values", () => {
    const snapshot = agg.getSnapshot();
    expect(snapshot.cost_per_token).toBe(0);
    expect(snapshot.total_session_cost).toBe(0);
    expect(snapshot.avg_latency_ms).toBe(0);
    expect(snapshot.failover_count).toBe(0);
    expect(snapshot.provider_success_rate).toBe(100);
    expect(snapshot.total_requests).toBe(0);
  });
});

describe("TelemetryAggregator — lifecycle", () => {
  it("reset clears all counters", () => {
    const agg = new TelemetryAggregator();
    agg.ingest({
      type: "gateway_request",
      timestamp: "",
      payload: { cost_per_token: 0.001, tokens_used: 100, latency_ms: 50, failover: true, status_code: 200 },
    });
    agg.reset();
    const s = agg.getSnapshot();
    expect(s.total_requests).toBe(0);
    expect(s.failover_count).toBe(0);
    agg.destroy();
  });

  it("start/stop interval manages lifecycle", () => {
    const agg = new TelemetryAggregator();
    let emitted = false;
    agg.setOnSnapshot(() => {
      emitted = true;
    });
    agg.start(50);
    agg.ingest({
      type: "gateway_request",
      timestamp: "",
      payload: { cost_per_token: 0.001, tokens_used: 100, latency_ms: 50, status_code: 200 },
    });
    // Wait for interval
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        agg.stop();
        expect(emitted).toBe(true);
        agg.destroy();
        resolve();
      }, 100);
    });
  });

  it("snapshot callback receives correct data", () => {
    const agg = new TelemetryAggregator();
    return new Promise<void>((resolve) => {
      agg.setOnSnapshot((snapshot) => {
        expect(snapshot.total_requests).toBe(1);
        expect(snapshot.avg_latency_ms).toBe(100);
        agg.destroy();
        resolve();
      });
      agg.start(30);
      agg.ingest({
        type: "gateway_request",
        timestamp: "",
        payload: { latency_ms: 100, status_code: 200 },
      });
    });
  });
});
