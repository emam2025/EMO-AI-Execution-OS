import { describe, it, expect } from "vitest";

interface FeedbackPayload {
  environment: { os: string; version: string; runtime: string; memoryUsage: string };
  category: string;
  description: string;
  logs: string[];
  trace: string;
  timestamp: number;
}

const SENSITIVE_PATTERNS = [
  /sk-[a-zA-Z0-9]{20,}/g,
  /AIza[0-9A-Za-z_-]{35,}/g,
  /ghp_[a-zA-Z0-9]{36,}/g,
  /Bearer\s+[a-zA-Z0-9_-]{20,}/gi,
  /(?:password|secret|api[_-]?key)\s*[:=]\s*['"][^'"]+['"]/gi,
  /[\w.-]+@[\w.-]+\.\w{2,}/g,
];

function scrubText(text: string): string {
  let scrubbed = text;
  for (const pattern of SENSITIVE_PATTERNS) {
    scrubbed = scrubbed.replace(pattern, "[REDACTED]");
  }
  return scrubbed;
}

function validatePayload(payload: FeedbackPayload): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  if (!payload.description || payload.description.trim().length === 0) errors.push("missing description");
  if (!payload.category) errors.push("missing category");
  if (payload.timestamp <= 0) errors.push("invalid timestamp");
  for (const log of payload.logs) {
    if (log !== scrubText(log)) errors.push("log contains unredacted sensitive data");
  }
  if (payload.description !== scrubText(payload.description)) errors.push("description contains unredacted sensitive data");
  return { valid: errors.length === 0, errors };
}

describe("Feedback Submission — Privacy Scrubbing", () => {
  it("should redact API keys from descriptions", () => {
    const input = "Error using key sk-abc123def456ghi789jklmno for OpenAI";
    const scrubbed = scrubText(input);
    expect(scrubbed).not.toContain("sk-abc123def456ghi789jklmno");
    expect(scrubbed).toContain("[REDACTED]");
  });

  it("should redact email addresses", () => {
    const input = "User john.doe@company.com reported an issue";
    const scrubbed = scrubText(input);
    expect(scrubbed).not.toContain("john.doe@company.com");
    expect(scrubbed).toContain("[REDACTED]");
  });

  it("should redact passwords and secrets", () => {
    const input = `password = "supersecret123"`;
    const scrubbed = scrubText(input);
    expect(scrubbed).not.toContain("supersecret123");
    expect(scrubbed).toContain("[REDACTED]");
  });

  it("should validate complete payload", () => {
    const payload: FeedbackPayload = {
      environment: { os: "macOS", version: "0.1.0", runtime: "node", memoryUsage: "256MB" },
      category: "bug",
      description: "Agent crashed on startup",
      logs: ["Error: connection refused"],
      trace: "",
      timestamp: Date.now(),
    };
    const result = validatePayload(payload);
    expect(result.valid).toBe(true);
  });

  it("should reject payload with sensitive data in logs", () => {
    const payload: FeedbackPayload = {
      environment: { os: "macOS", version: "0.1.0", runtime: "node", memoryUsage: "256MB" },
      category: "bug",
      description: "API error",
      logs: ["api_key=sk-test12345678901234567890"],
      trace: "",
      timestamp: Date.now(),
    };
    const result = validatePayload(payload);
    expect(result.valid).toBe(false);
  });
});
