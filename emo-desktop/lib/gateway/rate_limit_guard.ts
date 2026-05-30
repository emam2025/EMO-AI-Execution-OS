/**
 * RateLimitGuard — Per-provider RPM enforcement with local block list.
 *
 * Blocks requests exceeding the configured RPM (requests per minute)
 * and maintains a local block list with cooldown.
 *
 * Zero core dependencies — pure TypeScript rate limiter.
 */

export interface RateLimitConfig {
  max_rpm: number;       // max requests per minute
  cooldown_seconds: number; // how long to block after exceeding
}

export interface BlockedRequest {
  provider_id: string;
  timestamp: number;
  reason: string;
  blocked_until: number;
}

const DEFAULT_CONFIG: RateLimitConfig = {
  max_rpm: 60,
  cooldown_seconds: 30,
};

export class RateLimitGuard {
  private config: Map<string, RateLimitConfig>;
  private requestCount: Map<string, number[]>;
  private blockedRequests: BlockedRequest[];
  private blockUntil: Map<string, number>;

  constructor() {
    this.config = new Map();
    this.requestCount = new Map();
    this.blockedRequests = [];
    this.blockUntil = new Map();
  }

  setProviderConfig(provider_id: string, config: Partial<RateLimitConfig>): void {
    const existing = this.config.get(provider_id) ?? DEFAULT_CONFIG;
    this.config.set(provider_id, { ...existing, ...config });
  }

  removeProvider(provider_id: string): void {
    this.config.delete(provider_id);
    this.requestCount.delete(provider_id);
    this.blockUntil.delete(provider_id);
  }

  getProviderConfig(provider_id: string): RateLimitConfig {
    return this.config.get(provider_id) ?? DEFAULT_CONFIG;
  }

  isBlocked(provider_id: string): boolean {
    const until = this.blockUntil.get(provider_id) ?? 0;
    if (until > Date.now()) return true;
    if (until > 0) {
      // Cooldown expired — unblock
      this.blockUntil.delete(provider_id);
    }
    return false;
  }

  getBlockedRequests(): BlockedRequest[] {
    const now = Date.now();
    return this.blockedRequests.filter((b) => b.blocked_until > now);
  }

  /**
   * Attempt to consume a request slot.
   * Returns true if allowed, false if rate limited.
   */
  tryConsume(provider_id: string): boolean {
    if (this.isBlocked(provider_id)) return false;

    const cfg = this.getProviderConfig(provider_id);
    const now = Date.now();
    const windowStart = now - 60_000;

    let timestamps = this.requestCount.get(provider_id) ?? [];
    // Prune timestamps outside the 60-second window
    timestamps = timestamps.filter((t) => t > windowStart);

    if (timestamps.length >= cfg.max_rpm) {
      // Blocked — record it
      const blocked_until = now + cfg.cooldown_seconds * 1000;
      this.blockUntil.set(provider_id, blocked_until);
      this.blockedRequests.push({
        provider_id,
        timestamp: now,
        reason: `Exceeded max_rpm=${cfg.max_rpm}`,
        blocked_until,
      });
      return false;
    }

    timestamps.push(now);
    this.requestCount.set(provider_id, timestamps);
    return true;
  }

  /**
   * Get remaining capacity for a provider in the current window.
   */
  getRemainingCapacity(provider_id: string): number {
    if (this.isBlocked(provider_id)) return 0;
    const cfg = this.getProviderConfig(provider_id);
    const now = Date.now();
    const timestamps = (this.requestCount.get(provider_id) ?? []).filter(
      (t) => t > now - 60_000,
    );
    return Math.max(0, cfg.max_rpm - timestamps.length);
  }

  reset(): void {
    this.config.clear();
    this.requestCount.clear();
    this.blockedRequests = [];
    this.blockUntil.clear();
  }
}
