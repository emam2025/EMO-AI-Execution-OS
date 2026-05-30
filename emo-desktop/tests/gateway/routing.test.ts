/**
 * Test: GatewayRouter — Routing Decision Logic
 *
 * Verifies:
 *   - Optimal provider selection based on weight/latency/cost
 *   - User preference honouring
 *   - User preference failover when degraded
 *   - No active providers → "none" fallback
 *   - Score ordering (best provider has highest score)
 *   - Degraded status penalty applied
 *   - Configurable latency/cost weights
 *   - Provider add/remove lifecycle
 *   - Empty provider list edge case
 *   - Reset clears all state
 */
import { describe, it, expect } from "vitest";
import { GatewayRouter, type ProviderHealth } from "../../lib/gateway/router";

function makeProvider(
  id: string,
  overrides?: Partial<ProviderHealth>,
): ProviderHealth {
  return {
    provider_id: id,
    status: "active",
    latency_ms: 100,
    cost_per_token: 0.001,
    rpm_remaining: 50,
    cost_tier: "low",
    weight: 0.5,
    ...overrides,
  };
}

describe("GatewayRouter — selectRoute", () => {
  it("selects provider with lowest latency when latency_weight=1", () => {
    const router = new GatewayRouter({ latency_weight: 1, cost_weight: 0 });
    router.upsertProvider(makeProvider("openai", { latency_ms: 200, cost_per_token: 0.002 }));
    router.upsertProvider(makeProvider("anthropic", { latency_ms: 50, cost_per_token: 0.005 }));
    const decision = router.selectRoute();
    expect(decision.selected_provider).toBe("anthropic");
    expect(decision.score).toBeGreaterThan(0.5);
  });

  it("selects provider with lowest cost when cost_weight=1", () => {
    const router = new GatewayRouter({ latency_weight: 0, cost_weight: 1 });
    router.upsertProvider(makeProvider("openai", { latency_ms: 200, cost_per_token: 0.002 }));
    router.upsertProvider(makeProvider("anthropic", { latency_ms: 50, cost_per_token: 0.005 }));
    router.upsertProvider(makeProvider("groq", { latency_ms: 300, cost_per_token: 0.0005 }));
    const decision = router.selectRoute();
    expect(decision.selected_provider).toBe("groq");
  });

  it("honours user preference when provider is active", () => {
    const router = new GatewayRouter();
    router.upsertProvider(makeProvider("openai"));
    router.upsertProvider(makeProvider("anthropic"));
    const decision = router.selectRoute("openai");
    expect(decision.selected_provider).toBe("openai");
    expect(decision.score).toBe(1.0);
    expect(decision.reason).toContain("User preference");
  });

  it("failover when user preference is degraded", () => {
    const router = new GatewayRouter();
    router.upsertProvider(makeProvider("openai", { status: "degraded", latency_ms: 5000 }));
    router.upsertProvider(makeProvider("anthropic", { status: "active", latency_ms: 100 }));
    const decision = router.selectRoute("openai");
    expect(decision.selected_provider).toBe("anthropic");
    expect(decision.reason).toContain("failover");
  });

  it("returns 'none' when no active providers", () => {
    const router = new GatewayRouter();
    router.upsertProvider(makeProvider("openai", { status: "down" }));
    router.upsertProvider(makeProvider("anthropic", { status: "down" }));
    const decision = router.selectRoute();
    expect(decision.selected_provider).toBe("none");
    expect(decision.score).toBe(0);
  });

  it("returns 'none' when provider list is empty", () => {
    const router = new GatewayRouter();
    const decision = router.selectRoute();
    expect(decision.selected_provider).toBe("none");
    expect(decision.alternatives).toHaveLength(0);
  });

  it("lists alternatives excluding selected", () => {
    const router = new GatewayRouter();
    router.upsertProvider(makeProvider("openai"));
    router.upsertProvider(makeProvider("anthropic"));
    router.upsertProvider(makeProvider("groq"));
    const decision = router.selectRoute();
    expect(decision.alternatives).not.toContain(decision.selected_provider);
    expect(decision.alternatives.length).toBe(2);
  });

  it("applies degraded status penalty in scoring", () => {
    const router = new GatewayRouter({ latency_weight: 0.5, cost_weight: 0.5 });
    router.upsertProvider(makeProvider("degraded-provider", { status: "degraded", latency_ms: 100, cost_per_token: 0.001 }));
    router.upsertProvider(makeProvider("healthy-provider", { status: "active", latency_ms: 100, cost_per_token: 0.001 }));
    const decision = router.selectRoute();
    expect(decision.selected_provider).toBe("healthy-provider");
  });

  it("upsertProvider replaces existing entry", () => {
    const router = new GatewayRouter();
    router.upsertProvider(makeProvider("openai", { latency_ms: 100 }));
    router.upsertProvider(makeProvider("openai", { latency_ms: 999 }));
    expect(router.getProvider("openai")?.latency_ms).toBe(999);
  });

  it("removeProvider removes entry", () => {
    const router = new GatewayRouter();
    router.upsertProvider(makeProvider("openai"));
    router.removeProvider("openai");
    expect(router.getProvider("openai")).toBeUndefined();
  });

  it("reset clears all providers", () => {
    const router = new GatewayRouter();
    router.upsertProvider(makeProvider("openai"));
    router.reset();
    expect(router.getProviders()).toHaveLength(0);
  });
});
