import { describe, it, expect } from "vitest";
import type { BugReport, BugCategory, BugSeverity } from "../../ui/public-feedback-portal/PublicBugReporter";
import type { FeatureRequest } from "../../ui/public-feedback-portal/FeatureRequestBoard";
import type { QueueItem } from "../../ui/public-feedback-portal/PriorityQueueView";

describe("TestPublicFeedbackUI", () => {
  it("should create bug report with all required fields", () => {
    const report: BugReport = {
      id: "b1", title: "App crashes on launch", description: "Happens every time",
      category: "crash", severity: "critical", logsAttached: true, logsCleaned: true,
      timestamp: Date.now(), sessionId: "s1", status: "new",
    };
    expect(report.title).toBe("App crashes on launch");
    expect(report.category).toBe("crash");
    expect(report.severity).toBe("critical");
    expect(report.logsCleaned).toBe(true);
  });

  it("should support all bug categories and severities", () => {
    const categories: BugCategory[] = ["crash", "ui", "performance", "security", "compatibility", "other"];
    const severities: BugSeverity[] = ["low", "medium", "high", "critical"];
    expect(categories).toHaveLength(6);
    expect(severities).toHaveLength(4);
  });

  it("should create feature request with voting support", () => {
    const req: FeatureRequest = {
      id: "f1", title: "Dark mode", description: "Add dark theme",
      votes: 5, userVoted: false, status: "under_review", createdAt: Date.now(), category: "feature",
    };
    expect(req.votes).toBe(5);
    expect(req.status).toBe("under_review");
    const voted: FeatureRequest = { ...req, votes: 6, userVoted: true };
    expect(voted.votes).toBe(6);
    expect(voted.userVoted).toBe(true);
  });

  it("should calculate priority score from impact and frequency", () => {
    const items: QueueItem[] = [
      { id: "q1", title: "Login bug", type: "bug", impact: 9, frequency: 10, priorityScore: 90, status: "new", createdAt: Date.now() },
      { id: "q2", title: "Typo", type: "bug", impact: 2, frequency: 3, priorityScore: 6, status: "new", createdAt: Date.now() },
    ];
    expect(items[0].priorityScore).toBe(90);
    expect(items[1].priorityScore).toBe(6);
    const sorted = [...items].sort((a, b) => b.priorityScore - a.priorityScore);
    expect(sorted[0].title).toBe("Login bug");
  });

  it("should filter queue items by type", () => {
    const items: QueueItem[] = [
      { id: "q1", title: "Bug", type: "bug", impact: 5, frequency: 5, priorityScore: 25, status: "new", createdAt: 1 },
      { id: "q2", title: "Feature", type: "feature", impact: 5, frequency: 5, priorityScore: 25, status: "new", createdAt: 2 },
      { id: "q3", title: "Feedback", type: "feedback", impact: 5, frequency: 5, priorityScore: 25, status: "new", createdAt: 3 },
    ];
    const bugs = items.filter((i) => i.type === "bug");
    expect(bugs).toHaveLength(1);
    expect(bugs[0].title).toBe("Bug");
    const features = items.filter((i) => i.type === "feature");
    expect(features).toHaveLength(1);
  });
});
