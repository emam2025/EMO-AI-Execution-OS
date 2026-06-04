import { logAuditEvent } from "../security/audit-logger";

export type AlertSeverity = "info" | "warning" | "critical" | "emergency";
export type AlertChannel = "email" | "webhook" | "logstream" | "pagerduty";

export interface AlertRule {
  name: string;
  metric: string;
  threshold: number;
  operator: "gt" | "lt" | "gte" | "lte" | "eq";
  severity: AlertSeverity;
  channel: AlertChannel;
  cooldownMs: number;
  lastFired: number;
}

export interface AlertEvent {
  id: string;
  ruleName: string;
  metric: string;
  value: number;
  threshold: number;
  severity: AlertSeverity;
  channel: AlertChannel;
  message: string;
  timestamp: number;
  acknowledged: boolean;
}

export interface LaunchReport {
  generatedAt: number;
  version: string;
  uptimeHours: number;
  totalAlerts: number;
  criticalAlerts: number;
  crashRate: number;
  avgLatency: number;
  activeUsers: number;
  healthy: boolean;
}

const rules: AlertRule[] = [];
const alertHistory: AlertEvent[] = [];
const MAX_HISTORY = 1000;
let alertCounter = 0;

function generateId(): string {
  return `alert_${Date.now().toString(36)}_${(alertCounter++).toString(36)}`;
}

export function setupAlertRules(): AlertRule[] {
  const defaults: AlertRule[] = [
    { name: "crash_rate_exceeded", metric: "crash_rate", threshold: 0.01, operator: "gt", severity: "critical", channel: "pagerduty", cooldownMs: 300000, lastFired: 0 },
    { name: "high_latency", metric: "avg_latency_ms", threshold: 2000, operator: "gt", severity: "warning", channel: "email", cooldownMs: 60000, lastFired: 0 },
    { name: "unsigned_update_detected", metric: "unsigned_update", threshold: 0, operator: "gt", severity: "emergency", channel: "pagerduty", cooldownMs: 0, lastFired: 0 },
    { name: "error_rate_spike", metric: "error_rate", threshold: 0.05, operator: "gt", severity: "warning", channel: "webhook", cooldownMs: 120000, lastFired: 0 },
    { name: "concurrent_users_peak", metric: "concurrent_users", threshold: 500, operator: "gt", severity: "info", channel: "logstream", cooldownMs: 60000, lastFired: 0 },
  ];
  rules.length = 0;
  rules.push(...defaults);
  return [...rules];
}

export function evaluateMetric(metric: string, value: number): AlertEvent[] {
  const triggered: AlertEvent[] = [];
  const now = Date.now();
  for (const rule of rules) {
    if (rule.metric !== metric) continue;
    if (now - rule.lastFired < rule.cooldownMs) continue;
    let fired = false;
    switch (rule.operator) {
      case "gt": fired = value > rule.threshold; break;
      case "lt": fired = value < rule.threshold; break;
      case "gte": fired = value >= rule.threshold; break;
      case "lte": fired = value <= rule.threshold; break;
      case "eq": fired = value === rule.threshold; break;
    }
    if (fired) {
      rule.lastFired = now;
      const alert: AlertEvent = {
        id: generateId(),
        ruleName: rule.name,
        metric,
        value,
        threshold: rule.threshold,
        severity: rule.severity,
        channel: rule.channel,
        message: `Alert: ${rule.name} — ${metric}=${value} (threshold=${rule.threshold})`,
        timestamp: now,
        acknowledged: false,
      };
      alertHistory.push(alert);
      if (alertHistory.length > MAX_HISTORY) alertHistory.shift();
      triggered.push(alert);
      logAuditEvent({
        type: "permission_violation",
        severity: rule.severity === "emergency" ? "critical" : rule.severity === "critical" ? "high" : "medium",
        source: "production-alerts",
        detail: `Alert fired: ${rule.name} (${metric}=${value}, threshold=${rule.threshold})`,
        metadata: { rule: rule.name, metric, value, threshold: rule.threshold, channel: rule.channel },
      });
    }
  }
  return triggered;
}

export function routeAlert(channel: AlertChannel, payload: AlertEvent): boolean {
  const validChannels: AlertChannel[] = ["email", "webhook", "logstream", "pagerduty"];
  if (!validChannels.includes(channel)) return false;
  if (channel === "logstream") {
    return true;
  }
  if (channel === "email") {
    return true;
  }
  if (channel === "webhook") {
    return true;
  }
  if (channel === "pagerduty") {
    return true;
  }
  return false;
}

export function generateLaunchReport(version: string, uptimeHours: number, activeUsers: number, crashRate: number, avgLatency: number): LaunchReport {
  const critical = alertHistory.filter((a) => a.severity === "critical" || a.severity === "emergency");
  const healthy = crashRate <= 0.01 && avgLatency <= 2000 && critical.length === 0;
  return {
    generatedAt: Date.now(),
    version,
    uptimeHours,
    totalAlerts: alertHistory.length,
    criticalAlerts: critical.length,
    crashRate,
    avgLatency,
    activeUsers,
    healthy,
  };
}

export function acknowledgeAlert(alertId: string): boolean {
  const alert = alertHistory.find((a) => a.id === alertId);
  if (!alert) return false;
  alert.acknowledged = true;
  return true;
}

export function getAlertHistory(severity?: AlertSeverity): AlertEvent[] {
  if (severity) {
    return alertHistory.filter((a) => a.severity === severity);
  }
  return [...alertHistory];
}

export function clearAlertHistory(): void {
  alertHistory.length = 0;
  rules.length = 0;
}
