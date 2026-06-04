/**
 * Opt-In Manager — Telemetry & Crash Reporting Consent
 *
 * Policies:
 *   1. Telemetry and crash reporting are DISABLED by default.
 *   2. User must explicitly consent via requestTelemetryConsent().
 *   3. Consent can be revoked at any time via revokeTelemetryConsent().
 *   4. No data is sent until consent is granted.
 *   5. All collected data is anonymized (no prompts, keys, or content).
 */
import type { ProviderId } from "../credentials/types";

// ──────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────

export type TelemetryConsent = "granted" | "denied" | "undecided";

export interface TelemetryPayload {
  metric: string;
  value: number | string;
  tags?: Record<string, string>;
  timestamp: number;
}

export interface CrashReportConfig {
  submitURL: string;
  uploadToServer: boolean;
}

// ──────────────────────────────────────────────
// State
// ──────────────────────────────────────────────

const CONSENT_KEY = "emo-telemetry-consent";
let _consent: TelemetryConsent = loadConsent();
const _metricsBuffer: TelemetryPayload[] = [];

// ──────────────────────────────────────────────
// Consent persistence
// ──────────────────────────────────────────────

function loadConsent(): TelemetryConsent {
  try {
    const stored = localStorage.getItem(CONSENT_KEY);
    if (stored === "granted") return "granted";
    if (stored === "denied") return "denied";
    return "undecided";
  } catch {
    return "undecided";
  }
}

function saveConsent(value: TelemetryConsent): void {
  _consent = value;
  try {
    localStorage.setItem(CONSENT_KEY, value);
  } catch {
    // Storage unavailable — keep in-memory state
  }
}

// ──────────────────────────────────────────────
// Public API
// ──────────────────────────────────────────────

/**
 * Returns current telemetry consent status.
 * Default: "undecided" (never sent)
 */
export function getTelemetryConsent(): TelemetryConsent {
  return _consent;
}

/**
 * Shows a consent dialog explaining what data is collected.
 * In production, this renders a modal dialog. In test/simulation,
 * it returns the current consent status.
 *
 * Data collected (all anonymized, no content):
 *   - Crash reports (stack traces, no prompts or keys)
 *   - Performance metrics (CPU, memory, latency)
 *   - Feature usage (anonymized, no personal data)
 *
 * Data NEVER collected:
 *   - API keys
 *   - Agent prompts or results
 *   - File contents
 *   - Personal information
 */
export function requestTelemetryConsent(): Promise<TelemetryConsent> {
  // In production: show a modal dialog with accept/decline buttons.
  // Returns a promise that resolves when the user makes a choice.
  return new Promise((resolve) => {
    // Placeholder: in real UI, this opens a consent dialog.
    // For now, default to denied unless previously granted.
    const current = getTelemetryConsent();
    if (current !== "undecided") {
      resolve(current);
    } else {
      // Simulate dialog: default to denied
      saveConsent("denied");
      resolve("denied");
    }
  });
}

/**
 * Grants telemetry consent explicitly.
 */
export function grantTelemetryConsent(): void {
  saveConsent("granted");
}

/**
 * Denies telemetry consent explicitly.
 */
export function denyTelemetryConsent(): void {
  saveConsent("denied");
}

/**
 * Revokes previously granted consent.
 * Stops all data transmission immediately.
 */
export function revokeTelemetryConsent(): void {
  saveConsent("denied");
  _metricsBuffer.length = 0;
}

/**
 * Returns true if telemetry data can be sent.
 */
export function isTelemetryEnabled(): boolean {
  return _consent === "granted";
}

/**
 * Initializes the crash reporter.
 * Only activates if telemetry consent has been granted.
 */
export function initCrashReporter(config: CrashReportConfig): { initialized: boolean; reason?: string } {
  if (!isTelemetryEnabled()) {
    return { initialized: false, reason: "telemetry not consented" };
  }
  if (!config.submitURL) {
    return { initialized: false, reason: "no submit URL configured" };
  }
  // In production: crashReporter.init({ submitURL, uploadToServer: config.uploadToServer })
  return { initialized: true };
}

/**
 * Sends an anonymized metric.
 * No-op unless telemetry consent has been granted.
 */
export function sendMetric(name: string, value: number | string, tags?: Record<string, string>): boolean {
  if (!isTelemetryEnabled()) {
    return false;
  }

  const payload: TelemetryPayload = {
    metric: name,
    value,
    tags,
    timestamp: Date.now(),
  };

  // Buffer for batch send
  _metricsBuffer.push(payload);

  // In production: enqueue for batch HTTP POST
  return true;
}

/**
 * Returns the current metrics buffer (for testing).
 */
export function getMetricsBuffer(): readonly TelemetryPayload[] {
  return _metricsBuffer;
}

/**
 * Clears the metrics buffer.
 */
export function clearMetricsBuffer(): void {
  _metricsBuffer.length = 0;
}

/**
 * Resets consent to undecided (for testing).
 */
export function resetConsent(): void {
  _consent = "undecided";
  try {
    localStorage.removeItem(CONSENT_KEY);
  } catch {
    // Storage unavailable
  }
  _metricsBuffer.length = 0;
}
