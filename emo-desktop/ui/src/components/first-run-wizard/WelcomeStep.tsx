import React from "react";

interface WelcomeStepProps {
  onNext: () => void;
}

export const WelcomeStep: React.FC<WelcomeStepProps> = ({ onNext }) => {
  // Basic OS detection
  const osName =
    typeof navigator !== "undefined"
      ? navigator.userAgent.includes("Mac")
        ? "macOS"
        : navigator.userAgent.includes("Win")
          ? "Windows"
          : "Linux"
      : "Unknown";

  return (
    <div style={{ textAlign: "center", padding: "24px 0" }}>
      <div style={{ fontSize: "3rem", marginBottom: 16, opacity: 0.8 }}>⟁</div>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 8 }}>
        Welcome to EMO OS
      </h1>
      <p style={{ color: "#6b7280", fontSize: "0.9rem", lineHeight: 1.5, marginBottom: 24 }}>
        Your cognitive operating system for AI agent orchestration.
        <br />
        Detected platform: <strong>{osName}</strong>
      </p>
      <div
        className="glass-panel"
        style={{
          padding: 16,
          marginBottom: 24,
          textAlign: "left",
          fontSize: "0.85rem",
          lineHeight: 1.6,
        }}
      >
        <p style={{ fontWeight: 600, marginBottom: 8 }}>This wizard will help you:</p>
        <ul style={{ paddingLeft: 20, color: "#6b7280" }}>
          <li>Connect your AI provider accounts (OpenAI, Anthropic, etc.)</li>
          <li>Select your runtime mode (Local / Sandbox / Enterprise)</li>
          <li>Validate the IPC connection to the runtime service</li>
          <li>Launch your workspace</li>
        </ul>
      </div>
      <button
        onClick={onNext}
        style={{
          padding: "10px 32px",
          borderRadius: 8,
          border: "none",
          background: "#2563eb",
          color: "#fff",
          fontWeight: 600,
          fontSize: "0.9rem",
          cursor: "pointer",
          transition: "all 0.15s",
        }}
      >
        Get Started →
      </button>
    </div>
  );
};
