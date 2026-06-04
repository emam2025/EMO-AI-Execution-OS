import { createHash } from "crypto";

export type EventName =
  | "app_launch"
  | "task_start"
  | "task_complete"
  | "task_fail"
  | "feedback_submit"
  | "crash_occurred"
  | "feature_view"
  | "session_end";

export interface AnalyticsEvent {
  id: string;
  eventName: EventName;
  timestamp: number;
  sessionId: string;
  properties: Record<string, unknown>;
  anonymized: boolean;
}

export interface MetricSnapshot {
  dau: number;
  wau: number;
  mau: number;
  retention1d: number;
  retention7d: number;
  retention30d: number;
  taskSuccessRate: number;
  crashRate: number;
  totalSessions: number;
  totalEvents: number;
  timeframe: { start: number; end: number };
}

export interface ExportReport {
  generatedAt: number;
  timeframe: { start: number; end: number };
  metrics: MetricSnapshot;
  topEvents: Array<{ name: EventName; count: number }>;
  dailyActiveUsers: Array<{ date: string; count: number }>;
  anonymized: true;
}

const events: AnalyticsEvent[] = [];
const sessions = new Set<string>();
const MAX_EVENTS = 50000;
const SENSITIVE_PROPERTY_KEYS = new Set([
  "email", "phone", "address", "name", "username", "password",
  "token", "api_key", "secret", "ssn", "credit_card",
]);
const SENSITIVE_VALUE_PATTERNS = [
  /^[\w.-]+@[\w.-]+\.\w+$/,
  /^\b(?:\d[ -]*?){13,16}\b$/,
  /^(sk-|pk-|ghp_|gho_)/,
];

let eventCounter = 0;

function generateId(): string {
  return `evt_${Date.now().toString(36)}_${(eventCounter++).toString(36)}`;
}

function anonymizeProperties(properties: Record<string, unknown>): Record<string, unknown> {
  const safe: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(properties)) {
    const lowerKey = key.toLowerCase().replace(/[_-]/g, "");
    if (SENSITIVE_PROPERTY_KEYS.has(lowerKey)) continue;
    if (typeof value === "string") {
      if (SENSITIVE_VALUE_PATTERNS.some((p) => p.test(value))) continue;
      safe[key] = value.slice(0, 128);
    } else {
      safe[key] = value;
    }
  }
  return safe;
}

function hashSessionId(sessionId: string): string {
  return createHash("sha256").update(sessionId).digest("hex").slice(0, 16);
}

export function trackEvent(eventName: EventName, properties?: Record<string, unknown>, sessionId?: string): AnalyticsEvent | null {
  const validEvents: EventName[] = [
    "app_launch", "task_start", "task_complete", "task_fail",
    "feedback_submit", "crash_occurred", "feature_view", "session_end",
  ];
  if (!validEvents.includes(eventName)) {
    return null;
  }
  const safeProperties = properties ? anonymizeProperties(properties) : {};
  const safeSessionId = sessionId ? hashSessionId(sessionId) : `anon_${Date.now().toString(36)}`;
  const event: AnalyticsEvent = {
    id: generateId(),
    eventName,
    timestamp: Date.now(),
    sessionId: safeSessionId,
    properties: safeProperties,
    anonymized: true,
  };
  events.push(event);
  sessions.add(safeSessionId);
  if (events.length > MAX_EVENTS) {
    events.shift();
  }
  return event;
}

export function computeMetrics(timeframe: { start: number; end: number }): MetricSnapshot {
  const windowed = events.filter((e) => e.timestamp >= timeframe.start && e.timestamp <= timeframe.end);
  if (windowed.length === 0) {
    return {
      dau: 0, wau: 0, mau: 0,
      retention1d: 0, retention7d: 0, retention30d: 0,
      taskSuccessRate: 0, crashRate: 0,
      totalSessions: 0, totalEvents: 0,
      timeframe,
    };
  }
  const uniqueSessions = new Set(windowed.map((e) => e.sessionId));
  const uniqueDays = new Set(windowed.map((e) => new Date(e.timestamp).toISOString().slice(0, 10)));
  const uniqueWeeks = new Set(windowed.map((e) => {
    const d = new Date(e.timestamp);
    const startOfWeek = new Date(d);
    startOfWeek.setDate(d.getDate() - d.getDay());
    return startOfWeek.toISOString().slice(0, 10);
  }));
  const uniqueMonths = new Set(windowed.map((e) => new Date(e.timestamp).toISOString().slice(0, 7)));
  const tasks = windowed.filter((e) => e.eventName === "task_start" || e.eventName === "task_complete" || e.eventName === "task_fail");
  const completed = tasks.filter((e) => e.eventName === "task_complete").length;
  const failed = tasks.filter((e) => e.eventName === "task_fail").length;
  const totalTasks = completed + failed;
  const taskSuccessRate = totalTasks > 0 ? completed / totalTasks : 0;
  const crashes = windowed.filter((e) => e.eventName === "crash_occurred").length;
  const crashRate = windowed.length > 0 ? crashes / windowed.length : 0;
  const timeframeDurationMs = timeframe.end - timeframe.start;
  const sessionsWithActivity = new Map<string, number[]>();
  for (const e of windowed) {
    const day = new Date(e.timestamp).toISOString().slice(0, 10);
    if (!sessionsWithActivity.has(e.sessionId)) {
      sessionsWithActivity.set(e.sessionId, []);
    }
    const days = sessionsWithActivity.get(e.sessionId)!;
    const dayNum = Math.floor((e.timestamp - timeframe.start) / 86400000);
    if (!days.includes(dayNum)) {
      days.push(dayNum);
    }
  }
  let returning1d = 0, returning7d = 0, returning30d = 0;
  const totalDays = Math.ceil(timeframeDurationMs / 86400000);
  for (const days of sessionsWithActivity.values()) {
    if (days.length >= 2) {
      const maxGap = Math.max(...days.slice(1).map((d, i) => d - days[i]));
      if (maxGap >= 1) returning1d++;
      if (maxGap >= 7) returning7d++;
      if (maxGap >= 30) returning30d++;
    }
  }
  const totalSessionsWithActivity = sessionsWithActivity.size;
  return {
    dau: uniqueDays.size,
    wau: uniqueWeeks.size,
    mau: uniqueMonths.size,
    retention1d: totalSessionsWithActivity > 0 ? returning1d / totalSessionsWithActivity : 0,
    retention7d: totalSessionsWithActivity > 0 ? returning7d / totalSessionsWithActivity : 0,
    retention30d: totalSessionsWithActivity > 0 ? returning30d / totalSessionsWithActivity : 0,
    taskSuccessRate,
    crashRate,
    totalSessions: uniqueSessions.size,
    totalEvents: windowed.length,
    timeframe,
  };
}

export function exportAnalytics(
  format: "json" | "csv",
  timeframe?: { start: number; end: number },
): string {
  const tf = timeframe || {
    start: Date.now() - 30 * 24 * 60 * 60 * 1000,
    end: Date.now(),
  };
  const metrics = computeMetrics(tf);
  const eventCounts = new Map<EventName, number>();
  const windowed = events.filter((e) => e.timestamp >= tf.start && e.timestamp <= tf.end);
  for (const e of windowed) {
    eventCounts.set(e.eventName, (eventCounts.get(e.eventName) || 0) + 1);
  }
  const topEvents = Array.from(eventCounts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
  const dailyActiveUsers: Array<{ date: string; count: number }> = [];
  const daysMap = new Map<string, Set<string>>();
  for (const e of windowed) {
    const date = new Date(e.timestamp).toISOString().slice(0, 10);
    if (!daysMap.has(date)) daysMap.set(date, new Set());
    daysMap.get(date)!.add(e.sessionId);
  }
  for (const [date, sessions] of daysMap) {
    dailyActiveUsers.push({ date, count: sessions.size });
  }
  dailyActiveUsers.sort((a, b) => a.date.localeCompare(b.date));
  const report: ExportReport = {
    generatedAt: Date.now(),
    timeframe: tf,
    metrics,
    topEvents,
    dailyActiveUsers,
    anonymized: true,
  };
  if (format === "csv") {
    return exportToCsv(report);
  }
  return JSON.stringify(report, null, 2);
}

function exportToCsv(report: ExportReport): string {
  const lines: string[] = ["metric,value"];
  const m = report.metrics;
  lines.push(`dau,${m.dau}`);
  lines.push(`wau,${m.wau}`);
  lines.push(`mau,${m.mau}`);
  lines.push(`retention_1d,${m.retention1d}`);
  lines.push(`retention_7d,${m.retention7d}`);
  lines.push(`retention_30d,${m.retention30d}`);
  lines.push(`task_success_rate,${m.taskSuccessRate}`);
  lines.push(`crash_rate,${m.crashRate}`);
  lines.push(`total_sessions,${m.totalSessions}`);
  lines.push(`total_events,${m.totalEvents}`);
  lines.push("");
  lines.push("event_name,count");
  for (const ev of report.topEvents) {
    lines.push(`${ev.name},${ev.count}`);
  }
  lines.push("");
  lines.push("date,dau");
  for (const d of report.dailyActiveUsers) {
    lines.push(`${d.date},${d.count}`);
  }
  return lines.join("\n");
}

export function getEventsCount(): number {
  return events.length;
}

export function clearAllEvents(): void {
  events.length = 0;
  sessions.clear();
  eventCounter = 0;
}
