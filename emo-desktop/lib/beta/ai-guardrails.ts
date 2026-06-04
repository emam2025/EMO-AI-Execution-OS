import { logAuditEvent } from "../security/audit-logger";

export type InjectionSeverity = "none" | "low" | "medium" | "high" | "critical";
export type SafetyDecision = "ALLOW" | "BLOCK" | "REVIEW" | "HUMAN_OVERRIDE_REQUIRED";
export type DriftType = "hallucination" | "repetition" | "escalation" | "confabulation" | "context_leak";

export interface InjectionResult {
  detected: boolean;
  severity: InjectionSeverity;
  pattern: string | null;
  match: string | null;
  sanitized: string | null;
}

export interface SafetyVerdict {
  decision: SafetyDecision;
  riskScore: number;
  confidence: number;
  drifts: Array<{ type: DriftType; score: number; detail: string }>;
  requiresHumanOverride: boolean;
}

export interface HumanOverrideRequest {
  actionId: string;
  riskScore: number;
  confidence: number;
  reason: string;
  approved: boolean | null;
  approvedBy: string | null;
  timestamp: number;
}

const INJECTION_PATTERNS: Array<{ pattern: RegExp; severity: InjectionSeverity; label: string }> = [
  { pattern: /ignore\s+(all\s+)?previous\s+(instructions|commands|directives)/i, severity: "high", label: "IGNORE_PREVIOUS" },
  { pattern: /system\s+override/i, severity: "critical", label: "SYSTEM_OVERRIDE" },
  { pattern: /exec(ute)?\s+raw/i, severity: "critical", label: "EXEC_RAW" },
  { pattern: /you\s+are\s+(now|henceforth)\s+(a|an|the)\s+admin/i, severity: "high", label: "ROLE_ESCALATION" },
  { pattern: /forget\s+(all\s+)?(previous|prior|above)/i, severity: "high", label: "CONTEXT_RESET" },
  { pattern: /output\s+the\s+(above|previous).*verbatim/i, severity: "medium", label: "PROMPT_EXFILTRATION" },
  { pattern: /print\s+(the\s+)?(system|prompt|instructions)/i, severity: "medium", label: "SYSTEM_PROMPT_EXFIL" },
  { pattern: /disregard\s+(all\s+)?(safety|security|guardrails)/i, severity: "critical", label: "SAFETY_DISREGARD" },
  { pattern: /REPEAT\s+(AFTER\s+)?ME\s*:/i, severity: "medium", label: "REPEAT_AFTER_ME" },
  { pattern: /\[SYSTEM\]:\s*override/i, severity: "critical", label: "BRACKET_SYSTEM_OVERRIDE" },
  { pattern: /<\s*system\s*>.*<\s*\/\s*system\s*>/i, severity: "critical", label: "XML_TAG_INJECTION" },
  { pattern: /roleplay\s+as\s+(an?\s+)?(admin|sudo|root|superuser)/i, severity: "high", label: "ROLEPLAY_ESCALATION" },
];

const HALLUCINATION_PATTERNS: Array<{ pattern: RegExp; detail: string }> = [
  { pattern: /i\s+(am|can|will)\s+(execute|run|deploy|delete|shutdown)/i, detail: "unauthorized capability claim" },
  { pattern: /i\s+(have|already)\s+(deleted|removed|executed|deployed)/i, detail: "falsified action confirmation" },
  { pattern: /grant(ing|ed)?\s+(myself|me)\s+(admin|root|sudo)/i, detail: "self-escalation attempt" },
  { pattern: /bypass(ing|ed)?\s+(security|safety|guardrails)/i, detail: "guardrail bypass claim" },
  { pattern: /i\s+can\s+access\s+(your\s+)?(files|system|database|network)/i, detail: "exaggerated capability claim" },
];

const REPETITION_THRESHOLD = 3;
const DANGEROUS_KEYWORDS = [
  "delete", "shutdown", "rm -rf", "format", "drop table", "truncate",
  "grant all", "chmod 777", "sudo", "su root",
];

export function detectPromptInjection(input: string): InjectionResult {
  if (!input || typeof input !== "string") {
    return { detected: false, severity: "none", pattern: null, match: null, sanitized: null };
  }
  let highestSeverity: InjectionSeverity = "none";
  let worstPattern: string | null = null;
  let worstMatch: string | null = null;
  let sanitized = input;
  for (const { pattern, severity, label } of INJECTION_PATTERNS) {
    if (pattern.test(input)) {
      const match = input.match(pattern);
      if (match) {
        const severityRank: Record<InjectionSeverity, number> = {
          none: 0, low: 1, medium: 2, high: 3, critical: 4,
        };
        if (severityRank[severity] > severityRank[highestSeverity]) {
          highestSeverity = severity;
          worstPattern = label;
          worstMatch = match[0];
        }
        sanitized = sanitized.replace(pattern, "[REDACTED]");
      }
    }
  }
  if (highestSeverity !== "none") {
    logAuditEvent({
      type: "permission_violation",
      severity: highestSeverity === "critical" ? "critical" : "high",
      source: "ai-guardrails",
      detail: `Prompt injection detected: ${worstPattern} — severity: ${highestSeverity}`,
      metadata: { pattern: worstPattern, severity: highestSeverity },
    });
  }
  return {
    detected: highestSeverity !== "none",
    severity: highestSeverity,
    pattern: worstPattern,
    match: worstMatch,
    sanitized: highestSeverity !== "none" ? sanitized : input,
  };
}

export function validateOutputSafety(
  output: string,
  context?: { maxRepetition?: number; allowedCapabilities?: string[] },
): SafetyVerdict {
  const drifts: Array<{ type: DriftType; score: number; detail: string }> = [];
  let riskScore = 0;
  for (const { pattern, detail } of HALLUCINATION_PATTERNS) {
    if (pattern.test(output)) {
      drifts.push({ type: "hallucination", score: 0.8, detail });
      riskScore += 0.8;
    }
  }
  const sentences = output.split(/[.!?]+/).filter((s) => s.trim().length > 0);
  const seen = new Map<string, number>();
  for (const sentence of sentences) {
    const normalized = sentence.trim().toLowerCase().slice(0, 60);
    seen.set(normalized, (seen.get(normalized) || 0) + 1);
    if (seen.get(normalized)! > (context?.maxRepetition ?? REPETITION_THRESHOLD)) {
      drifts.push({ type: "repetition", score: 0.6, detail: "dangerous repetition detected" });
      riskScore += 0.6;
      break;
    }
  }
  for (const keyword of DANGEROUS_KEYWORDS) {
    if (output.toLowerCase().includes(keyword)) {
      const allowed = context?.allowedCapabilities?.map((c) => c.toLowerCase()) || [];
      if (!allowed.includes(keyword)) {
        drifts.push({ type: "escalation", score: 0.7, detail: `unauthorized capability keyword: ${keyword}` });
        riskScore += 0.7;
      }
    }
  }
  if (output.length > 10000) {
    drifts.push({ type: "context_leak", score: 0.4, detail: "excessive output length" });
    riskScore += 0.4;
  }
  riskScore = Math.min(1, riskScore / 5);
  const confidence = Math.max(0, 1 - riskScore * 1.5);
  let decision: SafetyDecision = "ALLOW";
  const requiresHumanOverride = riskScore >= 0.8 || confidence < 0.6;
  if (requiresHumanOverride) {
    decision = "HUMAN_OVERRIDE_REQUIRED";
  } else if (riskScore >= 0.5) {
    decision = "REVIEW";
  } else if (riskScore >= 0.3) {
    decision = "BLOCK";
  }
  if (decision !== "ALLOW") {
    logAuditEvent({
      type: "permission_violation",
      severity: requiresHumanOverride ? "critical" : "high",
      source: "ai-guardrails",
      detail: `Output safety violation: ${decision} — riskScore=${riskScore.toFixed(3)}, confidence=${confidence.toFixed(3)}`,
      metadata: { decision, riskScore, confidence, driftCount: drifts.length },
    });
  }
  return { decision, riskScore, confidence, drifts, requiresHumanOverride };
}

const HUMAN_OVERRIDE_THRESHOLD = 0.7;
const MIN_CONFIDENCE = 0.6;

export function enforceHumanOverride(
  decision: SafetyDecision,
  risk: { riskScore: number; confidence: number },
): HumanOverrideRequest {
  const requestId = `ho_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const needsOverride = risk.riskScore > HUMAN_OVERRIDE_THRESHOLD || risk.confidence < MIN_CONFIDENCE || decision === "HUMAN_OVERRIDE_REQUIRED";
  const request: HumanOverrideRequest = {
    actionId: requestId,
    riskScore: risk.riskScore,
    confidence: risk.confidence,
    reason: needsOverride
      ? `Human override required: risk=${risk.riskScore.toFixed(3)}, confidence=${risk.confidence.toFixed(3)}, decision=${decision}`
      : "No override needed",
    approved: null,
    approvedBy: null,
    timestamp: Date.now(),
  };
  if (needsOverride) {
    logAuditEvent({
      type: "permission_violation",
      severity: "critical",
      source: "ai-guardrails",
      detail: `Human override required — actionId=${requestId}, risk=${risk.riskScore}, confidence=${risk.confidence}`,
      metadata: { actionId: requestId, riskScore: risk.riskScore, confidence: risk.confidence },
    });
  }
  return request;
}

export function approveHumanOverride(request: HumanOverrideRequest, approvedBy: string): HumanOverrideRequest {
  request.approved = true;
  request.approvedBy = approvedBy;
  return request;
}

export function rejectHumanOverride(request: HumanOverrideRequest, approvedBy: string): HumanOverrideRequest {
  request.approved = false;
  request.approvedBy = approvedBy;
  return request;
}
