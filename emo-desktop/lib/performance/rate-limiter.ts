import { logAuditEvent } from "../security/audit-logger";

export interface RateLimitConfig {
  maxRequests: number;
  windowMs: number;
  maxConcurrent: number;
  burstAllowed: number;
}

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetAt: number;
  retryAfterMs: number;
  currentConcurrent: number;
}

export interface ClientBucket {
  clientId: string;
  tokens: number;
  lastRefill: number;
  concurrent: number;
  blockedUntil: number;
}

const DEFAULT_CONFIG: RateLimitConfig = {
  maxRequests: 60,
  windowMs: 60000,
  maxConcurrent: 5,
  burstAllowed: 10,
};

const buckets = new Map<string, ClientBucket>();
const blockedClients = new Map<string, number>();
const ENDPOINT_LIMITS = new Map<string, { maxRequests: number; windowMs: number }>();

export function configureEndpoint(endpoint: string, maxRequests: number, windowMs: number): void {
  ENDPOINT_LIMITS.set(endpoint, { maxRequests, windowMs });
}

const HIGH_RISK_PATTERNS = [
  /\/admin\//, /\/config\//, /\/debug\//, /\/internal\//,
  /\/\.env/, /\/\.git/, /\/api\/v1\/users\/\d+\/delete/,
];

function getClientBucket(clientId: string, config: RateLimitConfig): ClientBucket {
  let bucket = buckets.get(clientId);
  const now = Date.now();
  if (!bucket) {
    bucket = {
      clientId,
      tokens: config.maxRequests,
      lastRefill: now,
      concurrent: 0,
      blockedUntil: 0,
    };
    buckets.set(clientId, bucket);
  } else {
    const elapsed = now - bucket.lastRefill;
    const refillTokens = Math.floor(elapsed / (config.windowMs / config.maxRequests));
    if (refillTokens > 0) {
      bucket.tokens = Math.min(config.maxRequests + config.burstAllowed, bucket.tokens + refillTokens);
      bucket.lastRefill = now;
    }
  }
  if (now < bucket.blockedUntil) {
    bucket.tokens = 0;
  }
  return bucket;
}

export function checkRateLimit(clientId: string, endpoint: string, config?: Partial<RateLimitConfig>): RateLimitResult {
  const merged: RateLimitConfig = {
    ...DEFAULT_CONFIG,
    ...config,
    maxRequests: ENDPOINT_LIMITS.get(endpoint)?.maxRequests ?? config?.maxRequests ?? DEFAULT_CONFIG.maxRequests,
    windowMs: ENDPOINT_LIMITS.get(endpoint)?.windowMs ?? config?.windowMs ?? DEFAULT_CONFIG.windowMs,
  };
  const bucket = getClientBucket(clientId, merged);
  const now = Date.now();
  if (now < bucket.blockedUntil) {
    return {
      allowed: false,
      remaining: 0,
      resetAt: bucket.blockedUntil,
      retryAfterMs: bucket.blockedUntil - now,
      currentConcurrent: bucket.concurrent,
    };
  }
  const isHighRisk = HIGH_RISK_PATTERNS.some((p) => p.test(endpoint));
  if (isHighRisk) {
    merged.maxRequests = Math.ceil(merged.maxRequests / 2);
  }
  if (bucket.tokens < 1) {
    const resetAt = bucket.lastRefill + merged.windowMs;
    const retryAfterMs = Math.max(0, resetAt - now);
    logAuditEvent({
      type: "permission_violation",
      severity: "medium",
      source: "rate-limiter",
      detail: `Rate limit exceeded: client=${clientId}, endpoint=${endpoint}`,
      metadata: { clientId, endpoint, retryAfterMs },
    });
    return {
      allowed: false,
      remaining: 0,
      resetAt,
      retryAfterMs,
      currentConcurrent: bucket.concurrent,
    };
  }
  if (bucket.concurrent >= merged.maxConcurrent) {
    return {
      allowed: false,
      remaining: bucket.tokens,
      resetAt: now + 1000,
      retryAfterMs: 1000,
      currentConcurrent: bucket.concurrent,
    };
  }
  bucket.tokens -= 1;
  bucket.concurrent += 1;
  return {
    allowed: true,
    remaining: Math.floor(bucket.tokens),
    resetAt: bucket.lastRefill + merged.windowMs,
    retryAfterMs: 0,
    currentConcurrent: bucket.concurrent,
  };
}

export function releaseConcurrentSlot(clientId: string): void {
  const bucket = buckets.get(clientId);
  if (bucket) {
    bucket.concurrent = Math.max(0, bucket.concurrent - 1);
  }
}

export function blockClient(clientId: string, durationMs: number): void {
  const bucket = buckets.get(clientId);
  if (bucket) {
    bucket.blockedUntil = Date.now() + durationMs;
    bucket.tokens = 0;
  }
  logAuditEvent({
    type: "permission_violation",
    severity: "high",
    source: "rate-limiter",
    detail: `Client blocked: ${clientId} for ${durationMs}ms`,
    metadata: { clientId, durationMs },
  });
}

export function getRateLimitStatus(clientId: string): { remaining: number; concurrent: number; blocked: boolean } {
  const bucket = buckets.get(clientId);
  if (!bucket) {
    return { remaining: DEFAULT_CONFIG.maxRequests, concurrent: 0, blocked: false };
  }
  return {
    remaining: Math.floor(bucket.tokens),
    concurrent: bucket.concurrent,
    blocked: Date.now() < bucket.blockedUntil,
  };
}

export function clearAllRateLimits(): void {
  buckets.clear();
  blockedClients.clear();
  ENDPOINT_LIMITS.clear();
}
