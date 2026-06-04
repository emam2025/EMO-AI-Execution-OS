import { describe, it, expect, beforeEach } from "vitest";
import {
  checkRateLimit,
  releaseConcurrentSlot,
  blockClient,
  getRateLimitStatus,
  clearAllRateLimits,
  configureEndpoint,
} from "../../lib/performance/rate-limiter";
import {
  cacheResponse,
  getCachedResponse,
  purgeStaleCache,
  getCacheStats,
  clearAllCaches,
} from "../../lib/performance/cache-manager";

describe("TestRateLimitEnforcement", () => {
  beforeEach(() => {
    clearAllRateLimits();
  });

  it("should allow requests within limit", () => {
    const result = checkRateLimit("client-1", "/api/status", { maxRequests: 10, windowMs: 60000, maxConcurrent: 5, burstAllowed: 0 });
    expect(result.allowed).toBe(true);
    expect(result.remaining).toBe(9);
    expect(result.retryAfterMs).toBe(0);
    releaseConcurrentSlot("client-1");
  });

  it("should return 429 when limit exceeded", () => {
    const config = { maxRequests: 3, windowMs: 60000, maxConcurrent: 5, burstAllowed: 0 };
    checkRateLimit("client-2", "/api/test", config);
    checkRateLimit("client-2", "/api/test", config);
    checkRateLimit("client-2", "/api/test", config);
    const result = checkRateLimit("client-2", "/api/test", config);
    expect(result.allowed).toBe(false);
    expect(result.remaining).toBe(0);
    expect(result.retryAfterMs).toBeGreaterThan(0);
  });

  it("should block client and prevent any requests", () => {
    checkRateLimit("bad-client", "/api/test");
    blockClient("bad-client", 60000);
    const status = getRateLimitStatus("bad-client");
    expect(status.blocked).toBe(true);
    const result = checkRateLimit("bad-client", "/api/test");
    expect(result.allowed).toBe(false);
  });
});

describe("TestCacheHitRatio", () => {
  beforeEach(() => {
    clearAllCaches();
  });

  it("should store and retrieve cached responses", () => {
    const data = { status: "ok", version: "1.0.0" };
    const stored = cacheResponse("system-status", data, 60000);
    expect(stored).toBe(true);
    const retrieved = getCachedResponse<typeof data>("system-status");
    expect(retrieved).toEqual(data);
  });

  it("should return stale cache stats with zero on empty store", () => {
    const stats = getCacheStats();
    expect(stats.totalEntries).toBe(0);
    expect(stats.hitRate).toBe(0);
    expect(stats.missCount).toBe(0);
  });

  it("should evict expired entries via purge", () => {
    cacheResponse("expire-key", "data", -1);
    const purged = purgeStaleCache();
    expect(purged).toBe(1);
    const after = getCachedResponse("expire-key");
    expect(after).toBeNull();
  });

  it("should calculate hit rate correctly", () => {
    cacheResponse("hit-test", { x: 1 }, 60000);
    getCachedResponse("hit-test");
    getCachedResponse("hit-test");
    getCachedResponse("nonexistent");
    const stats = getCacheStats();
    expect(stats.hitCount).toBe(2);
    expect(stats.missCount).toBe(1);
    expect(stats.hitRate).toBeCloseTo(2 / 3, 2);
  });

  it("should reject oversized entries", () => {
    const bigData = "x".repeat(6 * 1024 * 1024);
    const result = cacheResponse("big-key", bigData);
    expect(result).toBe(false);
  });
});
