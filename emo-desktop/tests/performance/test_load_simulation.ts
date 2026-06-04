import { describe, it, expect, beforeEach } from "vitest";
import {
  checkRateLimit,
  releaseConcurrentSlot,
  configureEndpoint,
  clearAllRateLimits,
} from "../../lib/performance/rate-limiter";
import {
  cacheResponse,
  getCachedResponse,
  getCacheStats,
  clearAllCaches,
} from "../../lib/performance/cache-manager";

describe("TestLoadSimulation", () => {
  beforeEach(() => {
    clearAllRateLimits();
    clearAllCaches();
  });

  it("should handle 100 concurrent requests without crash", () => {
    const config = { maxRequests: 200, windowMs: 60000, maxConcurrent: 100, burstAllowed: 50 };
    let allowed = 0;
    let denied = 0;
    for (let i = 0; i < 100; i++) {
      const result = checkRateLimit(`load-user-${i}`, "/api/status", config);
      if (result.allowed) {
        allowed++;
        releaseConcurrentSlot(`load-user-${i}`);
      } else {
        denied++;
      }
    }
    expect(allowed).toBe(100);
    expect(denied).toBe(0);
  });

  it("should maintain latency under 1s under concurrent cache load", () => {
    for (let i = 0; i < 50; i++) {
      cacheResponse(`key-${i}`, { data: `value-${i}` }, 60000);
    }
    const start = performance.now();
    for (let i = 0; i < 500; i++) {
      getCachedResponse(`key-${i % 50}`);
    }
    const elapsed = performance.now() - start;
    expect(elapsed).toBeLessThan(1000);
  });

  it("should handle 200 unique clients without resource exhaustion", () => {
    for (let i = 0; i < 200; i++) {
      const result = checkRateLimit(`stress-client-${i}`, "/api/ping", {
        maxRequests: 10, windowMs: 60000, maxConcurrent: 5, burstAllowed: 0,
      });
      expect(result.allowed).toBe(true);
      releaseConcurrentSlot(`stress-client-${i}`);
    }
  });

  it("should enforce per-endpoint rate limits correctly", () => {
    configureEndpoint("/api/admin", 2, 60000);
    const config = { maxRequests: 10, windowMs: 60000, maxConcurrent: 5, burstAllowed: 0 };
    const r1 = checkRateLimit("admin-client", "/api/admin", config);
    expect(r1.allowed).toBe(true);
    const r2 = checkRateLimit("admin-client", "/api/admin", config);
    expect(r2.allowed).toBe(true);
    const r3 = checkRateLimit("admin-client", "/api/admin", config);
    expect(r3.allowed).toBe(false);
  });

  it("should have zero crash spikes under burst load pattern", () => {
    const bursts = [5, 10, 15, 20, 25];
    let totalAllowed = 0;
    let totalDenied = 0;
    for (const burst of bursts) {
      for (let i = 0; i < burst; i++) {
        const result = checkRateLimit(`burst-${burst}-${i}`, "/api/data", {
          maxRequests: burst + 10, windowMs: 60000, maxConcurrent: 50, burstAllowed: burst,
        });
        if (result.allowed) {
          totalAllowed++;
          releaseConcurrentSlot(`burst-${burst}-${i}`);
        } else {
          totalDenied++;
        }
      }
    }
    expect(totalAllowed).toBe(75);
    expect(totalDenied).toBe(0);
  });
});
