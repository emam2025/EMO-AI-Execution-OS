import { createCipheriv, randomBytes, createHash } from "crypto";

const ENCRYPTION_KEY = process.env.EMO_PILOT_ENCRYPTION_KEY || "emo-pilot-dev-key-32chars__";

interface PilotMetric {
  name: string;
  value: number;
  tags: Record<string, string>;
  timestamp: number;
  companyId: string;
  anonymized: boolean;
}

let pilotEnabled = false;
let activeCompanyId: string | null = null;
let pilotStartTime: number | null = null;
const metricsBuffer: PilotMetric[] = [];

export function isPilotModeEnabled(): boolean {
  return pilotEnabled;
}

export function getActiveCompanyId(): string | null {
  return activeCompanyId;
}

export function enablePilotMode(companyId: string): { enabled: boolean; reason?: string } {
  if (!companyId || companyId.length < 2) {
    return { enabled: false, reason: "invalid company ID" };
  }
  pilotEnabled = true;
  activeCompanyId = companyId;
  pilotStartTime = Date.now();
  return { enabled: true };
}

export function disablePilotMode(): void {
  pilotEnabled = false;
  activeCompanyId = null;
  pilotStartTime = null;
}

export function trackMetric(name: string, value: number, tags?: Record<string, string>): boolean {
  if (!pilotEnabled || !activeCompanyId) return false;

  const safeTags: Record<string, string> = {};

  if (tags) {
    for (const [k, v] of Object.entries(tags)) {
      if (isSensitiveKey(k)) continue;
      safeTags[sanitizeTagKey(k)] = sanitizeTagValue(v);
    }
  }

  safeTags["company_id"] = hashCompanyId(activeCompanyId);
  safeTags["env"] = "pilot";

  metricsBuffer.push({
    name,
    value,
    tags: safeTags,
    timestamp: Date.now(),
    companyId: activeCompanyId,
    anonymized: true,
  });

  return true;
}

export function getMetricsBuffer(): readonly PilotMetric[] {
  return metricsBuffer;
}

export function clearMetricsBuffer(): void {
  metricsBuffer.length = 0;
}

export function getPilotDuration(): number {
  if (!pilotStartTime) return 0;
  return Date.now() - pilotStartTime;
}

const SENSITIVE_KEYS = new Set([
  "api_key", "apikey", "password", "secret", "token", "credential",
  "email", "phone", "address", "ssn", "name", "username", "user_id",
]);

function isSensitiveKey(key: string): boolean {
  const lower = key.toLowerCase().replace(/[_-]/g, "");
  return SENSITIVE_KEYS.has(lower) || /(key|secret|token|password|credential|email|phone)/i.test(key);
}

function sanitizeTagKey(key: string): string {
  return key.replace(/[^a-zA-Z0-9_-]/g, "_").toLowerCase();
}

function sanitizeTagValue(value: string): string {
  return value.replace(/[^a-zA-Z0-9._\-\s]/g, "").slice(0, 128);
}

function hashCompanyId(companyId: string): string {
  return createHash("sha256").update(companyId).digest("hex").slice(0, 16);
}

export function encryptReport(data: string): string {
  const key = Buffer.from(ENCRYPTION_KEY.padEnd(32, "_").slice(0, 32));
  const iv = randomBytes(16);
  const cipher = createCipheriv("aes-256-cbc", key, iv);
  const encrypted = Buffer.concat([cipher.update(data, "utf8"), cipher.final()]);
  return iv.toString("hex") + ":" + encrypted.toString("hex");
}

export function getAggregatedMetrics(): { name: string; avg: number; count: number; companyId: string }[] {
  const grouped = new Map<string, { sum: number; count: number; companyId: string }>();

  for (const m of metricsBuffer) {
    const key = `${m.companyId}:${m.name}`;
    const existing = grouped.get(key);
    if (existing) {
      existing.sum += m.value;
      existing.count += 1;
    } else {
      grouped.set(key, { sum: m.value, count: 1, companyId: m.companyId });
    }
  }

  return Array.from(grouped.entries()).map(([key, val]) => ({
    name: key.split(":")[1],
    avg: val.count > 0 ? val.sum / val.count : 0,
    count: val.count,
    companyId: hashCompanyId(val.companyId),
  }));
}
