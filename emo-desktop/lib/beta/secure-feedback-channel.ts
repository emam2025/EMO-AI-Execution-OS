import { createCipheriv, randomBytes, createHash, timingSafeEqual } from "crypto";

export type FeedbackType = "bug" | "performance" | "security" | "feature" | "ux" | "crash" | "other";
export type FeedbackStatus = "new" | "acknowledged" | "triaged" | "resolved" | "dismissed";

export interface FeedbackEntry {
  id: string;
  type: FeedbackType;
  payload: string;
  metadata: Record<string, unknown>;
  timestamp: number;
  encryptedPayload: string;
  integrityHash: string;
  status: FeedbackStatus;
  companyHash: string;
}

export interface TelemetryPoint {
  metric: string;
  value: number;
  tags: Record<string, string>;
  timestamp: number;
  encryptedTimestamp: string;
}

export interface ChannelStatus {
  healthy: boolean;
  totalEntries: number;
  totalTelemetry: number;
  lastIntegrityCheck: number | null;
  tamperDetected: boolean;
  replayDetected: boolean;
}

const ENCRYPTION_KEY = process.env.EMO_BETA_ENCRYPTION_KEY || "emo-beta-enc-key-32characters!!";
const SENSITIVE_KEY_PATTERNS = [
  /api[-_]?key/i, /apikey/i, /secret/i, /token/i, /password/i,
  /credential/i, /private[-_]?key/i, /access[-_]?key/i,
  /email/i, /phone/i, /ssn/i, /social[-_]?security/i,
  /authorization/i, /bearer\s+\S+/i, /x-?auth/i,
];

const SENSITIVE_PATH_PATTERNS = [
  /\/home\/[^/]+\//, /\/Users\/[^/]+\//, /C:\\Users\\[^\\]+\\/i,
  /\/etc\/(passwd|shadow|sudoers)/, /\/\.ssh\//, /\/\.aws\//,
  /\/\.config\//, /\/\.git\//,
];

const feedbackEntries: FeedbackEntry[] = [];
const telemetryPoints: TelemetryPoint[] = [];
const MAX_ENTRIES = 10000;
let tamperDetected = false;
let replayDetected = false;
const usedIntegrityHashes = new Set<string>();

function generateId(): string {
  return "fb_" + randomBytes(12).toString("hex");
}

function encryptField(data: string): string {
  const key = Buffer.from(ENCRYPTION_KEY.padEnd(32, "_").slice(0, 32));
  const iv = randomBytes(16);
  const cipher = createCipheriv("aes-256-cbc", key, iv);
  const encrypted = Buffer.concat([cipher.update(data, "utf8"), cipher.final()]);
  return iv.toString("hex") + ":" + encrypted.toString("hex");
}

function hashForIntegrity(data: string): string {
  return createHash("sha256").update(data + ENCRYPTION_KEY).digest("hex");
}

function scrubSensitiveData(data: string): string {
  let scrubbed = data;
  for (const pattern of SENSITIVE_KEY_PATTERNS) {
    scrubbed = scrubbed.replace(pattern, "[REDACTED_KEY]");
  }
  for (const pattern of SENSITIVE_PATH_PATTERNS) {
    scrubbed = scrubbed.replace(pattern, "[REDACTED_PATH]/");
  }
  scrubbed = scrubbed.replace(/[\w.-]+@[\w.-]+\.\w+/g, "[REDACTED_EMAIL]");
  scrubbed = scrubbed.replace(/\b(?:\d[ -]*?){13,16}\b/g, "[REDACTED_CARD]");
  scrubbed = scrubbed.replace(/\b(sk-[a-zA-Z0-9]+|pk-[a-zA-Z0-9]+|ghp_[a-zA-Z0-9]+|gho_[a-zA-Z0-9]+|ghu_[a-zA-Z0-9]+)\b/g, "[REDACTED_API_KEY]");
  return scrubbed;
}

function hashCompany(company: string): string {
  return createHash("sha256").update(company).digest("hex").slice(0, 16);
}

export function submitFeedback(
  type: FeedbackType,
  payload: string,
  metadata?: Record<string, unknown>,
): FeedbackEntry | null {
  const validTypes: FeedbackType[] = ["bug", "performance", "security", "feature", "ux", "crash", "other"];
  if (!validTypes.includes(type)) {
    return null;
  }
  if (!payload || payload.length < 3) {
    return null;
  }
  const scrubbedPayload = scrubSensitiveData(payload);
  const scrubbedMetadata: Record<string, unknown> = {};
  if (metadata) {
    for (const [key, value] of Object.entries(metadata)) {
      const scrubbedKey = scrubSensitiveData(key);
      const scrubbedValue = typeof value === "string" ? scrubSensitiveData(value) : value;
      scrubbedMetadata[scrubbedKey] = scrubbedValue;
    }
  }
  const payloadStr = JSON.stringify({ payload: scrubbedPayload, metadata: scrubbedMetadata });
  const encryptedPayload = encryptField(payloadStr);
  const integrityHash = hashForIntegrity(payloadStr);
  const id = generateId();
  const entry: FeedbackEntry = {
    id,
    type,
    payload: scrubbedPayload,
    metadata: scrubbedMetadata,
    timestamp: Date.now(),
    encryptedPayload,
    integrityHash,
    status: "new",
    companyHash: scrubbedMetadata["company"] ? hashCompany(String(scrubbedMetadata["company"])) : "unknown",
  };
  if (usedIntegrityHashes.has(integrityHash)) {
    replayDetected = true;
    return null;
  }
  usedIntegrityHashes.add(integrityHash);
  feedbackEntries.push(entry);
  if (feedbackEntries.length > MAX_ENTRIES) {
    feedbackEntries.shift();
  }
  return entry;
}

export function collectBetaTelemetry(
  metric: string,
  value: number,
  tags?: Record<string, string>,
): TelemetryPoint | null {
  if (!metric || metric.length < 2) {
    return null;
  }
  if (typeof value !== "number" || isNaN(value)) {
    return null;
  }
  const safeTags: Record<string, string> = {};
  if (tags) {
    for (const [k, v] of Object.entries(tags)) {
      if (SENSITIVE_KEY_PATTERNS.some((p) => p.test(k))) continue;
      safeTags[k.replace(/[^a-zA-Z0-9_-]/g, "_").toLowerCase()] = String(v).slice(0, 64);
    }
  }
  const timestamp = Date.now();
  const encryptedTimestamp = encryptField(String(timestamp));
  const point: TelemetryPoint = {
    metric,
    value,
    tags: safeTags,
    timestamp,
    encryptedTimestamp,
  };
  telemetryPoints.push(point);
  if (telemetryPoints.length > MAX_ENTRIES) {
    telemetryPoints.shift();
  }
  return point;
}

export function verifyChannelIntegrity(): ChannelStatus {
  let hashMismatch = false;
  for (const entry of feedbackEntries) {
    const payloadStr = JSON.stringify({ payload: entry.payload, metadata: entry.metadata });
    const expectedHash = hashForIntegrity(payloadStr);
    if (expectedHash !== entry.integrityHash) {
      hashMismatch = true;
      break;
    }
  }
  tamperDetected = hashMismatch;
  return {
    healthy: !tamperDetected && !replayDetected,
    totalEntries: feedbackEntries.length,
    totalTelemetry: telemetryPoints.length,
    lastIntegrityCheck: Date.now(),
    tamperDetected,
    replayDetected,
  };
}

export function getFeedbackEntries(status?: FeedbackStatus): FeedbackEntry[] {
  if (status) {
    return feedbackEntries.filter((e) => e.status === status);
  }
  return [...feedbackEntries];
}

export function updateFeedbackStatus(id: string, status: FeedbackStatus): boolean {
  const entry = feedbackEntries.find((e) => e.id === id);
  if (!entry) return false;
  entry.status = status;
  return true;
}

export function getTelemetryPoints(metric?: string): TelemetryPoint[] {
  if (metric) {
    return telemetryPoints.filter((p) => p.metric === metric);
  }
  return [...telemetryPoints];
}

export function clearAllFeedback(): void {
  feedbackEntries.length = 0;
  telemetryPoints.length = 0;
  tamperDetected = false;
  replayDetected = false;
  usedIntegrityHashes.clear();
}
