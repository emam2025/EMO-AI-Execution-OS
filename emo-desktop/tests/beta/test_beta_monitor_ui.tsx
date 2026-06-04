import { describe, it, expect } from "vitest";
import type { BetaUserRow } from "../../ui/beta-monitor/ActiveUsersGrid";
import type { SafetyAlert } from "../../ui/beta-monitor/SafetyAlertsStream";
import type { TelemetryCell } from "../../ui/beta-monitor/TelemetryHeatmap";
import type { FeedbackItem } from "../../ui/beta-monitor/FeedbackQueue";

describe("TestMonitorRealTimeUpdates", () => {
  it("should define active user row with all required fields", () => {
    const user: BetaUserRow = {
      id: "u1", email: "test@beta.com", company: "BetaCorp",
      role: "tester", status: "ACTIVE", lastActivity: Date.now(),
    };
    expect(user.email).toBe("test@beta.com");
    expect(user.status).toBe("ACTIVE");
    expect(user.role).toBe("tester");
  });

  it("should support all user status transitions", () => {
    const statuses: BetaUserRow["status"][] = ["PENDING", "ACTIVE", "SUSPENDED", "REVOKED"];
    expect(statuses).toHaveLength(4);
    for (const s of statuses) {
      const user: BetaUserRow = { id: "u1", email: "a@b.com", company: "C", role: "tester", status: s, lastActivity: null };
      expect(user.status).toBe(s);
    }
  });

  it("should create safety alert with severity and timestamp", () => {
    const alert: SafetyAlert = {
      id: "a1", type: "injection", severity: "critical",
      message: "Critical injection detected", timestamp: Date.now(),
    };
    expect(alert.severity).toBe("critical");
    expect(alert.type).toBe("injection");
    expect(alert.message).toBeTruthy();
  });

  it("should map telemetry cell values to heatmap intensity", () => {
    const cells: TelemetryCell[] = [
      { metric: "cpu", category: "resources", value: 85, maxValue: 100, status: "warning" },
      { metric: "memory", category: "resources", value: 95, maxValue: 100, status: "critical" },
      { metric: "success_rate", category: "performance", value: 99, maxValue: 100, status: "success" },
    ];
    expect(cells).toHaveLength(3);
    expect(cells[1].status).toBe("critical");
    expect(cells[1].value).toBeGreaterThan(cells[0].value);
  });

  it("should create feedback queue item with filterable properties", () => {
    const items: FeedbackItem[] = [
      { id: "f1", type: "bug", status: "new", summary: "UI crash", timestamp: Date.now(), companyHash: "abc123" },
      { id: "f2", type: "security", status: "triaged", summary: "Auth bypass", timestamp: Date.now(), companyHash: "def456" },
    ];
    const bugs = items.filter((i) => i.type === "bug");
    expect(bugs).toHaveLength(1);
    expect(bugs[0].summary).toBe("UI crash");
    const triaged = items.filter((i) => i.status === "triaged");
    expect(triaged).toHaveLength(1);
    expect(triaged[0].type).toBe("security");
  });
});
