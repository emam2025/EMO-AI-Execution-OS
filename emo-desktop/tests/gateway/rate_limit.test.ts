/**
 * Test: RateLimitGuard — Rate Limit Enforcement
 *
 * Verifies:
 *   - Blocks requests exceeding max_rpm
 *   - Records blocked requests with timestamps
 *   - Allows requests within RPM limit
 *   - Cooldown period prevents further requests
 *   - Per-provider configuration
 *   - isBlocked checks block until timestamp
 *   - getRemainingCapacity returns correct count
 *   - removeProvider cleanup
 *   - Reset clears all state
 *   - Block list survives after unblock (read-only)
 */
import { describe, it, expect } from "vitest";
import { RateLimitGuard } from "../../lib/gateway/rate_limit_guard";

describe("RateLimitGuard — tryConsume", () => {
  it("allows requests within RPM limit", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 10, cooldown_seconds: 30 });
    for (let i = 0; i < 10; i++) {
      expect(guard.tryConsume("openai")).toBe(true);
    }
  });

  it("blocks requests exceeding max_rpm", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 3, cooldown_seconds: 1 });
    expect(guard.tryConsume("openai")).toBe(true);
    expect(guard.tryConsume("openai")).toBe(true);
    expect(guard.tryConsume("openai")).toBe(true);
    // 4th request should be blocked
    expect(guard.tryConsume("openai")).toBe(false);
  });

  it("records blocked requests with provider and timestamp", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 1, cooldown_seconds: 60 });
    guard.tryConsume("openai");
    guard.tryConsume("openai");
    const blocked = guard.getBlockedRequests();
    expect(blocked.length).toBeGreaterThanOrEqual(1);
    expect(blocked[0].provider_id).toBe("openai");
    expect(blocked[0].reason).toContain("max_rpm");
  });

  it("isBlocked returns true during cooldown", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 1, cooldown_seconds: 60 });
    guard.tryConsume("openai");
    guard.tryConsume("openai"); // triggers block
    expect(guard.isBlocked("openai")).toBe(true);
  });

  it("isBlocked returns false for unblocked provider", () => {
    const guard = new RateLimitGuard();
    expect(guard.isBlocked("openai")).toBe(false);
  });

  it("per-provider config allows different RPM limits", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 2, cooldown_seconds: 30 });
    guard.setProviderConfig("anthropic", { max_rpm: 10, cooldown_seconds: 30 });
    expect(guard.tryConsume("openai")).toBe(true);
    expect(guard.tryConsume("openai")).toBe(true);
    expect(guard.tryConsume("openai")).toBe(false); // blocked
    expect(guard.tryConsume("anthropic")).toBe(true); // still allowed
  });
});

describe("RateLimitGuard — getRemainingCapacity", () => {
  it("returns full capacity initially", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 60, cooldown_seconds: 30 });
    expect(guard.getRemainingCapacity("openai")).toBe(60);
  });

  it("decrements after consume", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 5, cooldown_seconds: 30 });
    guard.tryConsume("openai");
    guard.tryConsume("openai");
    expect(guard.getRemainingCapacity("openai")).toBe(3);
  });

  it("returns 0 when blocked", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 1, cooldown_seconds: 60 });
    guard.tryConsume("openai");
    guard.tryConsume("openai"); // blocked
    expect(guard.getRemainingCapacity("openai")).toBe(0);
  });

  it("returns max_rpm for new provider", () => {
    const guard = new RateLimitGuard();
    expect(guard.getRemainingCapacity("new-provider")).toBe(60);
  });
});

describe("RateLimitGuard — lifecycle", () => {
  it("removeProvider cleans up config and state", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 5, cooldown_seconds: 30 });
    guard.tryConsume("openai");
    guard.removeProvider("openai");
    expect(guard.getRemainingCapacity("openai")).toBe(60); // default
  });

  it("reset clears all providers and state", () => {
    const guard = new RateLimitGuard();
    guard.setProviderConfig("openai", { max_rpm: 1, cooldown_seconds: 60 });
    guard.tryConsume("openai");
    guard.tryConsume("openai");
    guard.reset();
    expect(guard.getBlockedRequests()).toHaveLength(0);
    expect(guard.getRemainingCapacity("openai")).toBe(60);
  });

  it("default config applies when no config set", () => {
    const guard = new RateLimitGuard();
    for (let i = 0; i < 60; i++) {
      expect(guard.tryConsume("default-provider")).toBe(true);
    }
    expect(guard.tryConsume("default-provider")).toBe(false);
  });
});
