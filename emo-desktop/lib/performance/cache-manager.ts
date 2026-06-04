export interface CacheEntry<T = unknown> {
  key: string;
  data: T;
  createdAt: number;
  expiresAt: number;
  accessCount: number;
  sizeBytes: number;
}

export interface CacheStats {
  totalEntries: number;
  totalSizeBytes: number;
  maxSizeBytes: number;
  hitCount: number;
  missCount: number;
  hitRate: number;
  oldestEntryAge: number;
}

const DEFAULT_MAX_SIZE = 50 * 1024 * 1024;
const DEFAULT_TTL_MS = 5 * 60 * 1000;

const store = new Map<string, CacheEntry>();
let maxSizeBytes = DEFAULT_MAX_SIZE;
let currentSizeBytes = 0;
let hitCount = 0;
let missCount = 0;

function estimateSize(data: unknown): number {
  const str = typeof data === "string" ? data : JSON.stringify(data);
  return Buffer.byteLength(str, "utf8");
}

export function cacheResponse<T>(key: string, data: T, ttlMs?: number): boolean {
  if (!key || key.length < 1) {
    return false;
  }
  const size = estimateSize(data);
  if (size > maxSizeBytes * 0.1) {
    return false;
  }
  while (currentSizeBytes + size > maxSizeBytes && store.size > 0) {
    let oldestKey: string | null = null;
    let oldestTime = Infinity;
    for (const [k, entry] of store) {
      if (entry.createdAt < oldestTime) {
        oldestTime = entry.createdAt;
        oldestKey = k;
      }
    }
    if (oldestKey) {
      evictEntry(oldestKey);
    } else {
      break;
    }
  }
  const now = Date.now();
  const ttl = ttlMs ?? DEFAULT_TTL_MS;
  const entry: CacheEntry<T> = {
    key,
    data,
    createdAt: now,
    expiresAt: now + ttl,
    accessCount: 0,
    sizeBytes: size,
  };
  const existing = store.get(key);
  if (existing) {
    currentSizeBytes -= existing.sizeBytes;
  }
  store.set(key, entry as CacheEntry);
  currentSizeBytes += size;
  return true;
}

export function getCachedResponse<T>(key: string): T | null {
  const entry = store.get(key);
  if (!entry) {
    missCount++;
    return null;
  }
  if (Date.now() > entry.expiresAt) {
    evictEntry(key);
    missCount++;
    return null;
  }
  entry.accessCount++;
  hitCount++;
  return entry.data as T;
}

export function purgeStaleCache(): number {
  const now = Date.now();
  let purged = 0;
  for (const [key, entry] of store) {
    if (now > entry.expiresAt) {
      evictEntry(key);
      purged++;
    }
  }
  return purged;
}

export function purgeAllCache(): void {
  store.clear();
  currentSizeBytes = 0;
}

export function getCacheStats(): CacheStats {
  purgeStaleCache();
  const totalRequests = hitCount + missCount;
  const now = Date.now();
  let oldestAge = 0;
  for (const entry of store.values()) {
    const age = now - entry.createdAt;
    if (age > oldestAge) oldestAge = age;
  }
  return {
    totalEntries: store.size,
    totalSizeBytes: currentSizeBytes,
    maxSizeBytes,
    hitCount,
    missCount,
    hitRate: totalRequests > 0 ? hitCount / totalRequests : 0,
    oldestEntryAge: oldestAge,
  };
}

export function setMaxCacheSize(bytes: number): void {
  maxSizeBytes = bytes;
  while (currentSizeBytes > maxSizeBytes && store.size > 0) {
    let oldestKey: string | null = null;
    let oldestTime = Infinity;
    for (const [k, entry] of store) {
      if (entry.createdAt < oldestTime) {
        oldestTime = entry.createdAt;
        oldestKey = k;
      }
    }
    if (oldestKey) {
      evictEntry(oldestKey);
    } else {
      break;
    }
  }
}

function evictEntry(key: string): void {
  const entry = store.get(key);
  if (entry) {
    currentSizeBytes -= entry.sizeBytes;
    store.delete(key);
  }
}

export function clearAllCaches(): void {
  purgeAllCache();
  hitCount = 0;
  missCount = 0;
}
