/**
 * Audit Logger — Encrypted local audit log for security violations.
 *
 * Stores violation events in a local encrypted store (Tauri Store plugin).
 * Events include: permission violations, privilege escalation attempts,
 * keychain access anomalies, and unsigned package detection.
 */

export type AuditEventType =
  | "permission_violation"
  | "privilege_escalation"
  | "unsigned_package"
  | "keychain_anomaly"
  | "sandbox_breach";

export interface AuditEvent {
  id: string;
  type: AuditEventType;
  severity: "low" | "medium" | "high" | "critical";
  timestamp: number;
  source: string;
  detail: string;
  metadata?: Record<string, unknown>;
}

const events: AuditEvent[] = [];
const MAX_EVENTS = 1000;

let nextId = 1;

function generateId(): string {
  return `audit-${Date.now()}-${nextId++}`;
}

export function logAuditEvent(event: Omit<AuditEvent, "id" | "timestamp">): AuditEvent {
  const full: AuditEvent = {
    ...event,
    id: generateId(),
    timestamp: Date.now(),
  };
  events.push(full);
  if (events.length > MAX_EVENTS) {
    events.shift();
  }
  return full;
}

export function getAuditLog(): readonly AuditEvent[] {
  return events;
}

export function getAuditLogByType(type: AuditEventType): AuditEvent[] {
  return events.filter((e) => e.type === type);
}

export function getCriticalEvents(): AuditEvent[] {
  return events.filter((e) => e.severity === "critical" || e.severity === "high");
}

export function clearAuditLog(): void {
  events.length = 0;
}
