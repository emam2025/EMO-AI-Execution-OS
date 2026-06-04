import React, { useState, useEffect, useCallback, useRef } from "react";

type Route = "dashboard" | "projects" | "agents" | "knowledge" | "skills" | "workflows" | "runtime-monitor" | "ai-gateway" | "settings" | "trace-explorer";

interface Command {
  id: string;
  label: string;
  route: Route;
  keywords: string[];
}

const COMMANDS: Command[] = [
  { id: "dash", label: "Go to Dashboard", route: "dashboard", keywords: ["home", "main", "overview"] },
  { id: "projects", label: "Open Projects", route: "projects", keywords: ["memory", "spaces", "sessions", "teams"] },
  { id: "agents", label: "Open Agents", route: "agents", keywords: ["health", "status", "active agents", "planner"] },
  { id: "knowledge", label: "Open Knowledge", route: "knowledge", keywords: ["memory", "tree", "graph", "traces"] },
  { id: "skills", label: "Open Skills", route: "skills", keywords: ["library", "capabilities", "tier"] },
  { id: "workflows", label: "Open Workflows", route: "workflows", keywords: ["execution", "timeline", "active"] },
  { id: "monitor", label: "Open Runtime Monitor", route: "runtime-monitor", keywords: ["metrics", "cpu", "memory", "performance", "health"] },
  { id: "gateway", label: "Open AI Gateway", route: "ai-gateway", keywords: ["providers", "routing", "cost", "llm", "model"] },
  { id: "trace", label: "Open Trace Explorer", route: "trace-explorer", keywords: ["execution", "traces", "timeline", "events"] },
  { id: "settings", label: "Open Settings", route: "settings", keywords: ["preferences", "config", "providers", "security"] },
];

interface CommandPaletteProps {
  onNavigate: (route: Route) => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ onNavigate }) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
        setQuery("");
        setSelectedIndex(0);
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const filtered = query.trim()
    ? COMMANDS.filter(
        (cmd) =>
          cmd.label.toLowerCase().includes(query.toLowerCase()) ||
          cmd.keywords.some((kw) => kw.toLowerCase().includes(query.toLowerCase())),
      )
    : COMMANDS;

  const handleSelect = useCallback(
    (cmd: Command) => {
      onNavigate(cmd.route);
      setOpen(false);
      setQuery("");
    },
    [onNavigate],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && filtered[selectedIndex]) {
      e.preventDefault();
      handleSelect(filtered[selectedIndex]);
    }
  };

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        display: "flex", alignItems: "flex-start", justifyContent: "center",
        paddingTop: "15vh",
        background: "rgba(0,0,0,0.3)", backdropFilter: "blur(4px)",
      }}
      onClick={() => setOpen(false)}
      role="dialog"
      aria-label="Command palette"
    >
      <div
        className="glass-panel"
        style={{
          width: 480, maxHeight: 360,
          display: "flex", flexDirection: "column", overflow: "hidden",
          animation: "smooth-scale-in 0.12s ease-out",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: "12px 14px", borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
          <input
            ref={inputRef}
            type="text"
            placeholder="Search screens and commands…"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelectedIndex(0); }}
            onKeyDown={handleKeyDown}
            className="glass-input"
            style={{ width: "100%" }}
            aria-label="Search commands"
          />
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: 4 }} role="listbox">
          {filtered.length === 0 && (
            <p style={{ padding: "24px 14px", textAlign: "center", color: "#9ca3af", fontSize: "0.85rem" }}>
              No matching screens
            </p>
          )}
          {filtered.map((cmd, i) => (
            <button
              key={cmd.id}
              role="option"
              aria-selected={i === selectedIndex}
              onClick={() => handleSelect(cmd)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                width: "100%", padding: "8px 12px", border: "none", borderRadius: 6,
                background: i === selectedIndex ? "rgba(59,130,246,0.1)" : "transparent",
                color: i === selectedIndex ? "#2563eb" : "#374151",
                fontWeight: i === selectedIndex ? 600 : 400,
                fontSize: "0.85rem", cursor: "pointer",
                transition: "all 0.1s ease-out", textAlign: "left",
              }}
            >
              {cmd.label}
            </button>
          ))}
        </div>
        <div style={{ padding: "6px 14px", borderTop: "1px solid rgba(0,0,0,0.04)", fontSize: "0.7rem", color: "#9ca3af", display: "flex", gap: 12 }}>
          <span>↑↓ Navigate</span>
          <span>↵ Open</span>
          <span>Esc Close</span>
        </div>
      </div>
    </div>
  );
};
