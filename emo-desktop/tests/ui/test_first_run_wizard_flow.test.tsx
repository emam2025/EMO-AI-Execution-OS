// @vitest-environment jsdom
import React from "react";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { FirstRunWizard } from "../../ui/src/components/first-run-wizard/Wizard";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("First-Run Wizard — 5-Step Flow", () => {
  it("renders Welcome step with EMO OS branding", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText("Welcome to EMO OS")).toBeDefined();
    expect(screen.getByText("Get Started →")).toBeDefined();
  });

  it("shows OS detection on Welcome step", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText(/macOS|Windows|Linux/)).toBeDefined();
  });

  it("Welcome → Get Started advances to Connect Models step", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    expect(screen.getByText("Connect AI Models")).toBeDefined();
  });

  it("Connect Models shows provider list", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    expect(screen.getByText("OpenAI")).toBeDefined();
    expect(screen.getByText("Anthropic")).toBeDefined();
    expect(screen.getByText("Groq")).toBeDefined();
  });

  it("Connect Models requires at least one provider", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    const nextBtn = screen.getByText("Next →") as HTMLButtonElement;
    expect(nextBtn.disabled).toBe(true);
  });

  it("Select Mode shows 3 runtime modes", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByText("Next →"));
    expect(screen.getByText("Local")).toBeDefined();
    expect(screen.getByText("Sandbox")).toBeDefined();
    expect(screen.getByText("Enterprise")).toBeDefined();
  });

  it("Validate step shows 4 checks", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByText("Next →"));
    fireEvent.click(screen.getByText("Next →"));
    expect(screen.getByText("emo-runtime-service health")).toBeDefined();
    expect(screen.getByText("IPC authentication")).toBeDefined();
    expect(screen.getByText("WebSocket event stream")).toBeDefined();
    expect(screen.getByText("Provider credentials (OS Keychain)")).toBeDefined();
  });

  it("Validate step passes all checks", async () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByText("Next →"));
    fireEvent.click(screen.getByText("Next →"));
    const done = await screen.findByText("All Checks Passed →", {}, { timeout: 5000 });
    expect(done).toBeDefined();
  });

  it("Launch step shows summary after validation", async () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByText("Next →"));
    fireEvent.click(screen.getByText("Next →"));
    const done = await screen.findByText("All Checks Passed →", {}, { timeout: 5000 });
    fireEvent.click(done);
    expect(screen.getByText("Ready to Launch")).toBeDefined();
    expect(screen.getByText("Launch Workspace →")).toBeDefined();
  });

  it("Back button navigates to previous step", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByText("← Back"));
    expect(screen.getByText("Welcome to EMO OS")).toBeDefined();
  });

  it("progress bar shows correct step number", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText(/Step 1 of 5/)).toBeDefined();
  });
});
