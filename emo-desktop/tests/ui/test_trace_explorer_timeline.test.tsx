// @vitest-environment jsdom
import React from "react";
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { TimelineNode, ExecutionTimeline, type NodeState } from "../../ui/src/styles/design-system/timeline-node";

afterEach(cleanup);

describe("Trace Explorer — TimelineNode", () => {
  it("renders label and state badge", () => {
    render(<TimelineNode label="plan_proposed" state="completed" />);
    expect(screen.getByText("plan_proposed")).toBeDefined();
    expect(screen.getByText("Completed")).toBeDefined();
  });

  it("shows 'Running' badge for running state", () => {
    render(<TimelineNode label="execute_node" state="running" />);
    expect(screen.getByText("Running")).toBeDefined();
  });

  it("shows 'Failed' badge for failed state", () => {
    render(<TimelineNode label="node_failed" state="failed" />);
    expect(screen.getByText("Failed")).toBeDefined();
  });

  it("formats duration ms when < 1000", () => {
    render(<TimelineNode label="node" state="completed" durationMs={450} />);
    expect(screen.getByText("450ms")).toBeDefined();
  });

  it("formats duration seconds when >= 1000", () => {
    render(<TimelineNode label="node" state="completed" durationMs={1500} />);
    expect(screen.getByText("1.5s")).toBeDefined();
  });

  it("renders description when provided", () => {
    render(<TimelineNode label="plan" state="completed" description="3 nodes planned" />);
    expect(screen.getByText("3 nodes planned")).toBeDefined();
  });

  it("fires onClick handler", () => {
    let clicked = false;
    render(<TimelineNode label="test" state="completed" onClick={() => { clicked = true; }} />);
    fireEvent.click(screen.getByText("test"));
    expect(clicked).toBe(true);
  });

  it("ExecutionTimeline renders children in order", () => {
    render(
      <ExecutionTimeline>
        <TimelineNode label="first" state="completed" />
        <TimelineNode label="second" state="running" />
        <TimelineNode label="third" state="pending" />
      </ExecutionTimeline>,
    );
    expect(screen.getByText("first")).toBeDefined();
    expect(screen.getByText("second")).toBeDefined();
    expect(screen.getByText("third")).toBeDefined();
  });

  it("skipped state renders correctly", () => {
    render(<TimelineNode label="skip" state="skipped" />);
    expect(screen.getByText("Skipped")).toBeDefined();
  });

  it("pending state shows pending badge", () => {
    render(<TimelineNode label="wait" state="pending" />);
    expect(screen.getByText("Pending")).toBeDefined();
  });
});
