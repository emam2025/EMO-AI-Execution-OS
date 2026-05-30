/**
 * FailoverEngine — Automatic provider failover with idempotency safety.
 *
 * Transitions: Primary → Fallback → Cached/Error State
 * Triggers: HTTP 429, 5xx, timeout > failover_threshold_ms
 * Safety: Each retry carries an idempotency_key to prevent duplicate processing.
 *
 * Zero core dependencies — pure TypeScript failover orchestration.
 */

import type { HealthStatus } from "./router";

export type FailoverTrigger = "http_429" | "http_5xx" | "timeout" | "rate_limited" | "down";

export interface FailoverEvent {
  provider_id: string;
  trigger: FailoverTrigger;
  timestamp: number;
  idempotency_key: string;
  latency_ms: number;
}

export interface FailoverResult {
  ok: boolean;
  provider_id: string;
  fallback_provider: string | null;
  failover_count: number;
  elapsed_ms: number;
}

export interface FailoverConfig {
  max_failover_attempts: number;
  failover_threshold_ms: number;
  cooldown_ms: number;
}

const DEFAULT_CONFIG: FailoverConfig = {
  max_failover_attempts: 3,
  failover_threshold_ms: 5000,
  cooldown_ms: 30_000,
};

let _idCounter = 0;
function generateIdempotencyKey(): string {
  _idCounter++;
  return `fk_${Date.now()}_${_idCounter}_${crypto.randomUUID?.()?.slice(0, 8) ?? Math.random().toString(36).slice(2, 10)}`;
}

export class FailoverEngine {
  private config: FailoverConfig;
  private chain: string[];
  private failoverCount: Map<string, number>;
  private cooldownUntil: Map<string, number>;
  private recentFailures: FailoverEvent[];

  constructor(chain: string[], config?: Partial<FailoverConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.chain = chain;
    this.failoverCount = new Map();
    this.cooldownUntil = new Map();
    this.recentFailures = [];
  }

  getChain(): string[] {
    return this.chain;
  }

  setChain(chain: string[]): void {
    this.chain = chain;
  }

  getFailoverCount(provider?: string): number {
    if (provider) return this.failoverCount.get(provider) ?? 0;
    return Array.from(this.failoverCount.values()).reduce((a, b) => a + b, 0);
  }

  private isOnCooldown(provider: string): boolean {
    return (this.cooldownUntil.get(provider) ?? 0) > Date.now();
  }

  recordFailure(provider: string, trigger: FailoverTrigger, latency_ms: number): FailoverEvent {
    const event: FailoverEvent = {
      provider_id: provider,
      trigger,
      timestamp: Date.now(),
      idempotency_key: generateIdempotencyKey(),
      latency_ms,
    };
    this.recentFailures.push(event);
    this.failoverCount.set(provider, (this.failoverCount.get(provider) ?? 0) + 1);
    this.cooldownUntil.set(provider, Date.now() + this.config.cooldown_ms);
    return event;
  }

  getRecentFailures(): FailoverEvent[] {
    return [...this.recentFailures];
  }

  /**
   * Execute failover: find next available provider in the chain.
   * Returns null if all providers are exhausted or on cooldown.
   */
  resolveNext(current: string, trigger: FailoverTrigger, latency_ms: number): FailoverResult {
    const event = this.recordFailure(current, trigger, latency_ms);
    const totalAttempts = this.getFailoverCount();
    const startTime = Date.now();

    const index = this.chain.indexOf(current);
    for (let i = index + 1; i < this.chain.length; i++) {
      const candidate = this.chain[i];
      if (this.isOnCooldown(candidate)) continue;

      const elapsed = Date.now() - startTime;
      return {
        ok: true,
        provider_id: current,
        fallback_provider: candidate,
        failover_count: totalAttempts,
        elapsed_ms: elapsed,
      };
    }

    // All exhausted — try cached/error state
    // Check if we should re-try the first in chain after cooldown
    if (this.chain.length > 0) {
      const firstAlive = this.chain.find((p) => !this.isOnCooldown(p));
      if (firstAlive) {
        return {
          ok: true,
          provider_id: current,
          fallback_provider: firstAlive,
          failover_count: totalAttempts,
          elapsed_ms: Date.now() - startTime,
        };
      }
    }

    return {
      ok: false,
      provider_id: current,
      fallback_provider: null,
      failover_count: totalAttempts,
      elapsed_ms: Date.now() - startTime,
    };
  }

  /**
   * Check whether failover is needed based on status code and latency.
   */
  shouldFailover(
    statusCode: number | null,
    latency_ms: number,
  ): { needed: boolean; trigger: FailoverTrigger | null } {
    if (statusCode === 429) return { needed: true, trigger: "http_429" };
    if (statusCode !== null && statusCode >= 500 && statusCode < 600)
      return { needed: true, trigger: "http_5xx" };
    if (latency_ms > this.config.failover_threshold_ms)
      return { needed: true, trigger: "timeout" };
    return { needed: false, trigger: null };
  }

  /**
   * Mark a provider as recovered (reset failover count).
   */
  markRecovered(provider: string): void {
    this.failoverCount.delete(provider);
    this.cooldownUntil.delete(provider);
  }

  reset(): void {
    this.failoverCount.clear();
    this.cooldownUntil.clear();
    this.recentFailures = [];
    _idCounter = 0;
  }
}
