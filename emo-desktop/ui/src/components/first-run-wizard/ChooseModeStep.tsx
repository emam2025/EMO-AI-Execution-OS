import React from "react";

type RuntimeMode = "local" | "hybrid" | "cloud";

interface ChooseModeStepProps {
  selected: RuntimeMode;
  onSelect: (mode: RuntimeMode) => void;
  onNext: () => void;
  onBack: () => void;
}

const MODES: { id: RuntimeMode; label: string; description: string; icon: string }[] = [
  {
    id: "local",
    label: "Local",
    description: "Run everything on your machine. Best for privacy, offline work, and development.",
    icon: "💻",
  },
  {
    id: "hybrid",
    label: "Hybrid",
    description: "Local runtime with cloud AI models. Balance of privacy and performance.",
    icon: "☁️",
  },
  {
    id: "cloud",
    label: "Cloud",
    description: "Fully cloud-hosted. Zero local compute, best for teams and production.",
    icon: "🌐",
  },
];

export const ChooseModeStep: React.FC<ChooseModeStepProps> = ({
  selected,
  onSelect,
  onNext,
  onBack,
}) => {
  return (
    <div>
      <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 4 }}>Choose Your Mode</h2>
      <p style={{ color: "#6b7280", fontSize: "0.85rem", marginBottom: 16 }}>
        How do you want EMO AI to run?
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
        {MODES.map((mode) => {
          const isSelected = selected === mode.id;
          return (
            <button
              key={mode.id}
              onClick={() => onSelect(mode.id)}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 4,
                padding: "14px 16px",
                borderRadius: 10,
                border: isSelected ? "2px solid #3b82f6" : "1px solid rgba(0,0,0,0.08)",
                background: isSelected ? "rgba(59,130,246,0.06)" : "rgba(255,255,255,0.5)",
                cursor: "pointer",
                transition: "all 0.12s ease-out",
                textAlign: "left",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: "1.2rem" }}>{mode.icon}</span>
                <div>
                  <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>{mode.label}</span>
                </div>
                <div
                  style={{
                    marginLeft: "auto",
                    width: 16,
                    height: 16,
                    borderRadius: "50%",
                    border: isSelected ? "4px solid #3b82f6" : "2px solid #d1d5db",
                    transition: "all 0.15s",
                  }}
                />
              </div>
              <p style={{ margin: "2px 0 0 28px", color: "#6b7280", fontSize: "0.8rem" }}>
                {mode.description}
              </p>
            </button>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onBack} className="glass-input" style={{ padding: "8px 20px", cursor: "pointer" }}>
          ← Back
        </button>
        <button
          onClick={onNext}
          style={{
            padding: "8px 20px",
            borderRadius: 8,
            border: "none",
            background: "#2563eb",
            color: "#fff",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Next →
        </button>
      </div>
    </div>
  );
};
