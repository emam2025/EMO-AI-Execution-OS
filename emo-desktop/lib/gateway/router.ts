/**
 * GatewayRouter — Provider-agnostic routing engine with weight/latency/cost selection.
 *
 * Selects the optimal provider based on:
 *   - provider_health (active/degraded/down)
 *   - cost_tier (low/medium/high)
 *   - user_preference (provider_id override)
 *   - latency_weight vs cost_weight (normalised scores)
 *
 * Zero core dependencies — pure TypeScript routing logic.
 */

export type HealthStatus = "active" | "degraded" | "down";
export type CostTier = "low" | "medium" | "high";

export interface ProviderHealth {
  provider_id: string;
  status: HealthStatus;
  latency_ms: number;
  cost_per_token: number;
  rpm_remaining: number;
  cost_tier: CostTier;
  weight: number; // 0.0 – 1.0, higher = preferred
}

export interface RoutingDecision {
  selected_provider: string;
  alternatives: string[];
  score: number;
  reason: string;
}

export interface RouterConfig {
  latency_weight: number; // 0.0 – 1.0
  cost_weight: number;    // 0.0 – 1.0
  failover_threshold_ms: number; // max acceptable latency
}

const DEFAULT_CONFIG: RouterConfig = {
  latency_weight: 0.5,
  cost_weight: 0.5,
  failover_threshold_ms: 5000,
};

export class GatewayRouter {
  private config: RouterConfig;
  private providers: Map<string, ProviderHealth>;

  constructor(config?: Partial<RouterConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.providers = new Map();
  }

  upsertProvider(health: ProviderHealth): void {
    this.providers.set(health.provider_id, health);
  }

  removeProvider(provider_id: string): void {
    this.providers.delete(provider_id);
  }

  getProviders(): ProviderHealth[] {
    return Array.from(this.providers.values());
  }

  getProvider(id: string): ProviderHealth | undefined {
    return this.providers.get(id);
  }

  selectRoute(userPreference?: string): RoutingDecision {
    const active = this.getProviders().filter((p) => p.status !== "down");

    if (active.length === 0) {
      return {
        selected_provider: "none",
        alternatives: [],
        score: 0,
        reason: "No active providers available",
      };
    }

    // If user has a preference and it's active, honour it
    if (userPreference) {
      const preferred = active.find(
        (p) =>
          p.provider_id === userPreference && p.status === "active",
      );
      if (preferred) {
        return {
          selected_provider: preferred.provider_id,
          alternatives: active
            .filter((p) => p.provider_id !== preferred.provider_id)
            .map((p) => p.provider_id),
          score: 1.0,
          reason: "User preference",
        };
      }
      // User preference is down/degraded — failover
      const degraded = this.providers.get(userPreference);
      if (degraded && degraded.status === "degraded") {
        const best = this.scoreProviders(active.filter((p) => p.provider_id !== userPreference));
        if (best) {
          return {
            selected_provider: best.provider_id,
            alternatives: active
              .filter((p) => p.provider_id !== best.provider_id)
              .map((p) => p.provider_id),
            score: best.score,
            reason: `User preference '${userPreference}' degraded, failover to best alternative`,
          };
        }
      }
    }

    const best = this.scoreProviders(active);
    if (!best) {
      return {
        selected_provider: "none",
        alternatives: [],
        score: 0,
        reason: "No routable provider after scoring",
      };
    }

    return {
      selected_provider: best.provider_id,
      alternatives: active
        .filter((p) => p.provider_id !== best.provider_id)
        .map((p) => p.provider_id),
      score: best.score,
      reason: `Weighted score: latency=${this.config.latency_weight}, cost=${this.config.cost_weight}`,
    };
  }

  private scoreProviders(
    candidates: ProviderHealth[],
  ): (ProviderHealth & { score: number }) | null {
    if (candidates.length === 0) return null;

    const maxLatency = Math.max(...candidates.map((p) => p.latency_ms));
    const maxCost = Math.max(...candidates.map((p) => p.cost_per_token));
    const minLatency = Math.min(...candidates.map((p) => p.latency_ms));
    const minCost = Math.min(...candidates.map((p) => p.cost_per_token));

    const latencyRange = maxLatency - minLatency || 1;
    const costRange = maxCost - minCost || 1;

    const scored = candidates.map((p) => {
      // Normalise: lower is better → higher score
      const latencyScore = 1 - (p.latency_ms - minLatency) / latencyRange;
      const costScore = 1 - (p.cost_per_token - minCost) / costRange;
      const statusPenalty = p.status === "degraded" ? 0.3 : 0;

      const score =
        this.config.latency_weight * latencyScore +
        this.config.cost_weight * costScore -
        statusPenalty +
        p.weight * 0.2; // preference boost

      return { ...p, score };
    });

    scored.sort((a, b) => b.score - a.score);
    return scored[0];
  }

  reset(): void {
    this.providers.clear();
  }
}
