// @vitest-environment jsdom
import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { CommandPalette } from "../../ui/src/components/command-palette/CommandPalette";

afterEach(cleanup);

describe("CommandPalette — Navigation", () => {
  it("renders closed by default", () => {
    const onNav = vi.fn();
    const { container } = render(<CommandPalette onNavigate={onNav} />);
    expect(container.textContent).toBe("");
  });

  it("opens on Ctrl+K", () => {
    const onNav = vi.fn();
    render(<CommandPalette onNavigate={onNav} />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(screen.getByPlaceholderText("Search screens and commands…")).toBeDefined();
  });

  it("opens on Cmd+K", () => {
    const onNav = vi.fn();
    render(<CommandPalette onNavigate={onNav} />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByPlaceholderText("Search screens and commands…")).toBeDefined();
  });

  it("closes on Escape", () => {
    const onNav = vi.fn();
    render(<CommandPalette onNavigate={onNav} />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(screen.getByPlaceholderText("Search screens and commands…")).toBeDefined();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByPlaceholderText("Search screens and commands…")).toBeNull();
  });

  it("filters commands by typed query", () => {
    const onNav = vi.fn();
    render(<CommandPalette onNavigate={onNav} />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = screen.getByPlaceholderText("Search screens and commands…");
    fireEvent.change(input, { target: { value: "monitor" } });
    expect(screen.getByText("Open Runtime Monitor")).toBeDefined();
    expect(screen.queryByText("Go to Dashboard")).toBeNull();
  });

  it("shows empty state for no match", () => {
    const onNav = vi.fn();
    render(<CommandPalette onNavigate={onNav} />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = screen.getByPlaceholderText("Search screens and commands…");
    fireEvent.change(input, { target: { value: "zzzzz" } });
    expect(screen.getByText("No matching screens")).toBeDefined();
  });

  it("calls onNavigate on item click and closes palette", () => {
    const onNav = vi.fn();
    render(<CommandPalette onNavigate={onNav} />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(screen.getByText("Go to Dashboard"));
    expect(onNav).toHaveBeenCalledWith("dashboard");
    expect(screen.queryByPlaceholderText("Search screens and commands…")).toBeNull();
  });

  it("search matches keywords", () => {
    const onNav = vi.fn();
    render(<CommandPalette onNavigate={onNav} />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.change(screen.getByPlaceholderText("Search screens and commands…"), { target: { value: "cpu" } });
    expect(screen.getByText("Open Runtime Monitor")).toBeDefined();
  });

  it("shows all items when query is empty", () => {
    const onNav = vi.fn();
    render(<CommandPalette onNavigate={onNav} />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(screen.getByText("Go to Dashboard")).toBeDefined();
    expect(screen.getByText("Open Runtime Monitor")).toBeDefined();
    expect(screen.getByText("Open Trace Explorer")).toBeDefined();
    expect(screen.getByText("Open Model Gateway")).toBeDefined();
  });

  it("footer shows navigation hints", () => {
    const onNav = vi.fn();
    render(<CommandPalette onNavigate={onNav} />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(screen.getByText("↑↓ Navigate")).toBeDefined();
    expect(screen.getByText("↵ Open")).toBeDefined();
    expect(screen.getByText("Esc Close")).toBeDefined();
  });
});
