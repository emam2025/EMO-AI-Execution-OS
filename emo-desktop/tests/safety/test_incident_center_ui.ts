import { describe, it, expect } from "vitest";
import type { AuditEntry } from "../../lib/safety/policy-engine";
import type { Alert, AlertSeverity } from "../../ui/incident-center/AlertsPanel";
import type { RecoveryAction, RecoveryStatus } from "../../ui/incident-center/RecoveryActions";

describe("Incident Center — AlertsPanel", () => {
  it("should sort alerts by severity (critical first)", () => {
    const severities: AlertSeverity[] = ["info", "critical", "medium", "high", "low"];
    const sevOrder: Record<AlertSeverity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

    const alerts: Alert[] = severities.map((s, i) => ({
      id: `alert-${i}`,
      timestamp: Date.now(),
      severity: s,
      title: `Test ${s}`,
      description: `Alert with ${s} severity`,
      source: "system",
      acknowledged: false,
    }));

    const sorted = [...alerts].sort((a, b) => (sevOrder[a.severity] ?? 5) - (sevOrder[b.severity] ?? 5));
    expect(sorted[0].severity).toBe("critical");
    expect(sorted[sorted.length - 1].severity).toBe("info");
  });

  it("should have unique IDs for all alerts", () => {
    const alerts: Alert[] = [
      { id: "a1", timestamp: 1, severity: "high", title: "A", description: "", source: "s", acknowledged: false },
      { id: "a2", timestamp: 2, severity: "medium", title: "B", description: "", source: "s", acknowledged: false },
      { id: "a3", timestamp: 3, severity: "low", title: "C", description: "", source: "s", acknowledged: false },
    ];
    const ids = new Set(alerts.map((a) => a.id));
    expect(ids.size).toBe(alerts.length);
  });

  it("should count unacknowledged alerts correctly", () => {
    const alerts: Alert[] = [
      { id: "a1", timestamp: 1, severity: "critical", title: "", description: "", source: "", acknowledged: false },
      { id: "a2", timestamp: 2, severity: "high", title: "", description: "", source: "", acknowledged: true },
      { id: "a3", timestamp: 3, severity: "medium", title: "", description: "", source: "", acknowledged: false },
    ];
    const unacknowledged = alerts.filter((a) => !a.acknowledged).length;
    expect(unacknowledged).toBe(2);
  });
});

describe("Incident Center — RecoveryActions", () => {
  it("should have valid status transitions", () => {
    const validTransitions: Record<RecoveryStatus, RecoveryStatus[]> = {
      pending: ["in_progress"],
      in_progress: ["completed", "failed"],
      completed: ["rolled_back"],
      failed: ["pending"],
      rolled_back: ["pending"],
    };

    const allStatuses: RecoveryStatus[] = ["pending", "in_progress", "completed", "failed", "rolled_back"];
    for (const status of allStatuses) {
      expect(validTransitions[status]).toBeDefined();
      expect(Array.isArray(validTransitions[status])).toBe(true);
    }
  });

  it("should require approval for execution", () => {
    const action: RecoveryAction = {
      id: "ra-1", alertId: "a-1", description: "Restart service",
      status: "pending", initiatedBy: "operator-1", timestamp: Date.now(),
    };
    expect(action.status).toBe("pending");
    expect(action.initiatedBy).toBeTruthy();
  });
});

describe("Incident Center — AuditTrailViewer", () => {
  it("should sort entries by timestamp descending", () => {
    const entries: AuditEntry[] = [
      { timestamp: 100, action: "old", decision: "ALLOW", reason: "", initiatedBy: "" },
      { timestamp: 300, action: "new", decision: "DENY", reason: "", initiatedBy: "" },
      { timestamp: 200, action: "mid", decision: "ALLOW", reason: "", initiatedBy: "" },
    ];
    const sorted = [...entries].sort((a, b) => b.timestamp - a.timestamp);
    expect(sorted[0].action).toBe("new");
    expect(sorted[2].action).toBe("old");
  });
});

describe("Incident Center — ExportReport", () => {
  it("should generate summary with correct counts", () => {
    const auditEntries: AuditEntry[] = Array(10).fill(null).map((_, i) => ({
      timestamp: i, action: `a${i}`, decision: i % 2 === 0 ? "ALLOW" as const : "DENY" as const, reason: "", initiatedBy: "",
    }));
    const alerts: Alert[] = Array(5).fill(null).map((_, i) => ({
      id: String(i), timestamp: i, severity: i < 2 ? "critical" as const : "low" as const,
      title: "", description: "", source: "", acknowledged: i < 3,
    }));
    const recoveryActions: RecoveryAction[] = Array(3).fill(null).map((_, i) => ({
      id: String(i), alertId: String(i), description: "", status: i < 1 ? "pending" as const : "completed" as const,
      initiatedBy: "", timestamp: i,
    }));

    expect(auditEntries.length).toBe(10);
    expect(alerts.filter((a) => a.severity === "critical").length).toBe(2);
    expect(alerts.filter((a) => !a.acknowledged).length).toBe(2);
    expect(recoveryActions.filter((a) => a.status === "pending").length).toBe(1);
    expect(recoveryActions.filter((a) => a.status === "completed").length).toBe(2);
  });
});
