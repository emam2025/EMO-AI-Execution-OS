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
  it("renders Welcome step with EMO AI branding", () => {
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
  });

  it("Connect Models requires at least one provider", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    const nextBtn = screen.getByText("Next →") as HTMLButtonElement;
    expect(nextBtn.disabled).toBe(true);
  });

  it("Choose Mode shows Local/Hybrid/Cloud options", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByText("Next →"));
    expect(screen.getByText("Local")).toBeDefined();
    expect(screen.getByText("Hybrid")).toBeDefined();
    expect(screen.getByText("Cloud")).toBeDefined();
  });

  it("Create Project step accepts project name", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByText("Next →"));
    fireEvent.click(screen.getByText("Next →"));
    expect(screen.getByText("Create Your First Project")).toBeDefined();
    const input = screen.getByPlaceholderText("e.g. My First AI Project");
    expect(input).toBeDefined();
  });

  it("Launch step shows summary with project and mode", () => {
    render(<FirstRunWizard onComplete={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByText("Next →"));
    fireEvent.click(screen.getByText("Next →"));
    const input = screen.getByPlaceholderText("e.g. My First AI Project");
    fireEvent.change(input, { target: { value: "Test Project" } });
    fireEvent.click(screen.getByText("Next →"));
    expect(screen.getByText("Ready to Launch")).toBeDefined();
    expect(screen.getByText("Launch Workspace →")).toBeDefined();
  });

  it("completes flow in localStorage on launch", () => {
    const onComplete = vi.fn();
    render(<FirstRunWizard onComplete={onComplete} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText("Get Started →"));
    fireEvent.click(screen.getByText("OpenAI"));
    fireEvent.click(screen.getByText("Next →"));
    fireEvent.click(screen.getByText("Next →"));
    const input = screen.getByPlaceholderText("e.g. My First AI Project");
    fireEvent.change(input, { target: { value: "P" } });
    fireEvent.click(screen.getByText("Next →"));
    fireEvent.click(screen.getByText("Launch Workspace →"));
    expect(onComplete).toHaveBeenCalled();
    expect(localStorage.getItem("emo-first-run-completed")).toBe("true");
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
