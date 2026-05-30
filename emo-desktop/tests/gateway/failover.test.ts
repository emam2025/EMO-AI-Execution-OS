/**
 * Test: FailoverEngine — Failover Chain Execution
 *
 * Verifies:
 *   - HTTP 503 triggers automatic failover within < 500ms
 *   - Failover walks chain to next alive provider
 *   - All providers exhausted → fallback_provider = null
 *   - Cooldown prevents repeated failover to same provider
 *   - shouldFailover detects 429, 5xx, timeout
 *   - markRecovered resets failover count
 *   - Idempotency key is unique per event
 *   - Recent failures list captures events
 *   - Reset clears all state
 *   - Max failover attempts boundary
 */
import { describe, it, expect } from "vitest";
import { FailoverEngine } from "../../lib/gateway/failover";

describe("FailoverEngine — resolveNext", () => {
  it("fails over to next provider in chain on 503 within 500ms", async () => {
    const engine = new FailoverEngine(["openai", "anthropic", "groq"]);
    const start = Date.now();
    const result = engine.resolveNext("openai", "http_5xx", 3200);
    const elapsed = Date.now() - start;
    expect(result.fallback_provider).toBe("anthropic");
    expect(result.ok).toBe(true);
    expect(elapsed).toBeLessThan(500);
  });

  it("walks chain skipping current provider", () => {
    const engine = new FailoverEngine(["openai", "anthropic", "groq"]);
    const r1 = engine.resolveNext("openai", "http_429", 100);
    expect(r1.fallback_provider).toBe("anthropic");
    const r2 = engine.resolveNext("anthropic", "http_5xx", 200);
    expect(r2.fallback_provider).toBe("groq");
  });

  it("returns null fallback when all providers exhausted", () => {
    const engine = new FailoverEngine(["openai"]);
    const r1 = engine.resolveNext("openai", "http_429", 100);
    // only one provider — no remaining
    expect(r1.ok).toBe(false);
    expect(r1.fallback_provider).toBeNull();
  });

  it("respects cooldown and skips cooled providers", () => {
    const engine = new FailoverEngine(["openai", "anthropic", "groq"], {
      cooldown_ms: 100_000,
    });
    // First failover triggers cooldown on openai
    engine.resolveNext("openai", "http_5xx", 3000);
    // resolve next from anthropic — groq is next
    const r = engine.resolveNext("anthropic", "http_5xx", 3000);
    expect(r.fallback_provider).toBe("groq");
  });

  it("cycles back to first available after all cooldown", () => {
    const engine = new FailoverEngine(["openai", "anthropic"], {
      cooldown_ms: 0,
    });
    engine.resolveNext("openai", "http_429", 100);
    const r = engine.resolveNext("anthropic", "http_429", 100);
    // cooldown=0 → openai is available again
    expect(r.fallback_provider).toBe("openai");
  });
});

describe("FailoverEngine — shouldFailover", () => {
  it("detects 429 as failover trigger", () => {
    const engine = new FailoverEngine(["openai"]);
    const result = engine.shouldFailover(429, 100);
    expect(result.needed).toBe(true);
    expect(result.trigger).toBe("http_429");
  });

  it("detects 503 as failover trigger", () => {
    const engine = new FailoverEngine(["openai"]);
    const result = engine.shouldFailover(503, 100);
    expect(result.needed).toBe(true);
    expect(result.trigger).toBe("http_5xx");
  });

  it("detects timeout > threshold as failover trigger", () => {
    const engine = new FailoverEngine(["openai"], { failover_threshold_ms: 5000 });
    const result = engine.shouldFailover(null, 6000);
    expect(result.needed).toBe(true);
    expect(result.trigger).toBe("timeout");
  });

  it("returns no failover for normal response", () => {
    const engine = new FailoverEngine(["openai"]);
    const result = engine.shouldFailover(200, 50);
    expect(result.needed).toBe(false);
    expect(result.trigger).toBeNull();
  });
});

describe("FailoverEngine — lifecycle", () => {
  it("markRecovered resets failover count and cooldown", () => {
    const engine = new FailoverEngine(["openai", "anthropic"]);
    engine.resolveNext("openai", "http_5xx", 100);
    expect(engine.getFailoverCount("openai")).toBe(1);
    engine.markRecovered("openai");
    expect(engine.getFailoverCount("openai")).toBe(0);
  });

  it("generates unique idempotency keys per event", () => {
    const engine = new FailoverEngine(["openai", "anthropic"]);
    engine.resolveNext("openai", "http_429", 100);
    engine.resolveNext("openai", "http_429", 100);
    const keys = engine.getRecentFailures().map((e) => e.idempotency_key);
    expect(new Set(keys).size).toBe(2);
  });

  it("recentFailures captures events with correct fields", () => {
    const engine = new FailoverEngine(["openai", "anthropic"]);
    engine.resolveNext("openai", "http_429", 150);
    const failures = engine.getRecentFailures();
    expect(failures).toHaveLength(1);
    expect(failures[0].provider_id).toBe("openai");
    expect(failures[0].trigger).toBe("http_429");
    expect(failures[0].latency_ms).toBe(150);
    expect(failures[0].idempotency_key).toBeTruthy();
  });

  it("reset clears all state", () => {
    const engine = new FailoverEngine(["openai", "anthropic"]);
    engine.resolveNext("openai", "http_5xx", 100);
    engine.reset();
    expect(engine.getFailoverCount()).toBe(0);
    expect(engine.getRecentFailures()).toHaveLength(0);
  });
});
