import React from "react";

interface LaunchStepProps {
  providers: string[];
  mode: string;
  projectName: string;
  validationPassed: boolean;
  onLaunch: () => void;
  onBack: () => void;
}

export const LaunchStep: React.FC<LaunchStepProps> = ({
  providers,
  mode,
  projectName,
  validationPassed,
  onLaunch,
  onBack,
}) => {
  return (
    <div style={{ textAlign: "center", padding: "16px 0" }}>
      <div
        style={{
          fontSize: "2.5rem",
          marginBottom: 12,
          opacity: validationPassed ? 0.8 : 0.4,
        }}
      >
        {validationPassed ? "⟁" : "◌"}
      </div>
      <h2 style={{ fontSize: "1.3rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 8 }}>
        Ready to Launch
      </h2>

      <div
        className="glass-panel"
        style={{
          padding: 16,
          marginBottom: 24,
          textAlign: "left",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
          <span style={{ color: "#6b7280" }}>Runtime Mode</span>
          <span style={{ fontWeight: 600, textTransform: "capitalize" }}>{mode}</span>
        </div>
        {projectName && (
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
            <span style={{ color: "#6b7280" }}>Project</span>
            <span style={{ fontWeight: 600 }}>{projectName}</span>
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
          <span style={{ color: "#6b7280" }}>Connected Providers</span>
          <span style={{ fontWeight: 600 }}>{providers.length > 0 ? providers.join(", ") : "None"}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
          <span style={{ color: "#6b7280" }}>Validation</span>
          <span style={{ fontWeight: 600, color: validationPassed ? "#22c55e" : "#ef4444" }}>
            {validationPassed ? "All Checks Passed" : "Incomplete"}
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
          <span style={{ color: "#6b7280" }}>UI Version</span>
          <span style={{ fontWeight: 600 }}>v1.0.0</span>
        </div>
      </div>

      <p style={{ color: "#6b7280", fontSize: "0.85rem", marginBottom: 24 }}>
        Your workspace will open in Dashboard view. You can access the Command Palette anytime
        with <kbd style={{ background: "#e5e7eb", padding: "2px 6px", borderRadius: 4, fontSize: "0.75rem" }}>Ctrl+K</kbd>.
      </p>

      <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
        <button onClick={onBack} className="glass-input" style={{ padding: "8px 20px", cursor: "pointer" }}>
          ← Back
        </button>
        <button
          onClick={onLaunch}
          style={{
            padding: "10px 32px",
            borderRadius: 8,
            border: "none",
            background: validationPassed ? "#2563eb" : "#9ca3af",
            color: "#fff",
            fontWeight: 600,
            fontSize: "0.9rem",
            cursor: validationPassed ? "pointer" : "default",
          }}
          disabled={!validationPassed}
        >
          Launch Workspace →
        </button>
      </div>
    </div>
  );
};
