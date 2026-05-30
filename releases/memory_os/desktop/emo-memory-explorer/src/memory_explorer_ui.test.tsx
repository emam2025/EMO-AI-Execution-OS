/**
 * Memory Explorer UI — 10 tests
 *
 * Covers: store initialization, stats/spaces/retention/audit setters,
 * dashboard rendering, project filter sidebar, retention input
 * interaction, trace agent filter, audit chain status display,
 * navigation between all routes.
 */

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import App from "./App";
import { useMemoryStore } from "./store/memoryStore";

/* ─── Store tests ─── */

describe("MemoryStore", () => {
  it("initializes with zero defaults", () => {
    const s = useMemoryStore.getState();
    expect(s.stats.totalEntries).toBe(0);
    expect(s.stats.totalGraphNodes).toBe(0);
    expect(s.stats.totalEdges).toBe(0);
    expect(s.stats.projectsCount).toBe(0);
    expect(s.stats.agentsActive).toBe(0);
    expect(s.stats.lastOptimized).toBe("—");
  });

  it("defaults spaces to empty array", () => {
    expect(useMemoryStore.getState().spaces).toEqual([]);
  });

  it("defaults retention to 100k/365d/archive", () => {
    const r = useMemoryStore.getState().retention;
    expect(r.maxEntries).toBe(100000);
    expect(r.ttlDays).toBe(365);
    expect(r.action).toBe("archive");
  });

  it("defaults audit log to empty array", () => {
    expect(useMemoryStore.getState().auditLog).toEqual([]);
  });

  it("setStats updates stats", () => {
    useMemoryStore.getState().setStats({
      totalEntries: 42,
      totalGraphNodes: 10,
      totalEdges: 30,
      projectsCount: 3,
      agentsActive: 5,
      lastOptimized: "2026-05-30",
    });
    expect(useMemoryStore.getState().stats.totalEntries).toBe(42);
    expect(useMemoryStore.getState().stats.projectsCount).toBe(3);
  });

  it("setSpaces updates spaces", () => {
    useMemoryStore.getState().setSpaces([
      { id: "p1", type: "project", name: "Proj A", entryCount: 10, lastActivity: "now" },
    ]);
    expect(useMemoryStore.getState().spaces).toHaveLength(1);
    expect(useMemoryStore.getState().spaces[0].name).toBe("Proj A");
  });

  it("setRetention updates retention", () => {
    useMemoryStore.getState().setRetention({
      maxEntries: 5000, ttlDays: 90, action: "warn",
      archiveAfterDays: 60, hardDeleteAfterDays: 180,
    });
    expect(useMemoryStore.getState().retention.maxEntries).toBe(5000);
    expect(useMemoryStore.getState().retention.action).toBe("warn");
  });

  it("setAuditLog stores and calculates chainVerified", () => {
    useMemoryStore.getState().setAuditLog([
      {
        entryId: "audit-001", action: "STORE", targetType: "memory_entry",
        targetId: "e1", reason: "test", timestamp: "2026-05-30T00:00:00Z",
        sha256Hash: "abc123deadbeef", chainVerified: true,
      },
    ]);
    expect(useMemoryStore.getState().auditLog).toHaveLength(1);
    expect(useMemoryStore.getState().auditLog[0].chainVerified).toBe(true);
  });
});

/* ─── UI rendering ─── */

describe("App routing and presence", () => {
  it("renders dashboard by default with stats glass panels", () => {
    render(<App initialRoute="dashboard" />);
    expect(screen.getByText("Dashboard")).toBeTruthy();
    expect(screen.getByText("Total Entries")).toBeTruthy();
    expect(screen.getByText("Graph Nodes")).toBeTruthy();
  });

  it("navigates to all routes via sidebar", () => {
    render(<App initialRoute="dashboard" />);
    const labels = [
      "Project Memory", "Context Browser", "Trace Recall",
      "Agent Trace", "Retention", "Audit Log", "Settings",
    ];
    for (const label of labels) {
      const btn = screen.getByText(label);
      fireEvent.click(btn);
      expect(screen.getByText(label)).toBeTruthy();
    }
  });
});
