import React from "react";

interface ConnectModelsStepProps {
  selectedProviders: string[];
  onSelect: (providers: string[]) => void;
  onNext: () => void;
  onBack: () => void;
}

const AVAILABLE_PROVIDERS = [
  { id: "openai", label: "OpenAI", color: "#10a37f" },
  { id: "anthropic", label: "Anthropic", color: "#d97706" },
  { id: "groq", label: "Groq", color: "#7c3aed" },
  { id: "google", label: "Google AI", color: "#4285f4" },
  { id: "mistral", label: "Mistral AI", color: "#2563eb" },
  { id: "cohere", label: "Cohere", color: "#059669" },
];

export const ConnectModelsStep: React.FC<ConnectModelsStepProps> = ({
  selectedProviders,
  onSelect,
  onNext,
  onBack,
}) => {
  const toggle = (id: string) => {
    onSelect(
      selectedProviders.includes(id)
        ? selectedProviders.filter((p) => p !== id)
        : [...selectedProviders, id],
    );
  };

  return (
    <div>
      <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 4 }}>Connect AI Models</h2>
      <p style={{ color: "#6b7280", fontSize: "0.85rem", marginBottom: 16 }}>
        Select the providers you want to use. You can configure API keys later in Settings.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 24 }}>
        {AVAILABLE_PROVIDERS.map((p) => {
          const selected = selectedProviders.includes(p.id);
          return (
            <button
              key={p.id}
              onClick={() => toggle(p.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "10px 14px",
                borderRadius: 8,
                border: selected ? `2px solid ${p.color}` : "1px solid rgba(0,0,0,0.08)",
                background: selected ? `${p.color}08` : "rgba(255,255,255,0.5)",
                cursor: "pointer",
                transition: "all 0.12s ease-out",
                textAlign: "left",
              }}
            >
              <div
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: 4,
                  border: selected ? `2px solid ${p.color}` : "2px solid #d1d5db",
                  background: selected ? p.color : "transparent",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#fff",
                  fontSize: "0.65rem",
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {selected ? "✓" : ""}
              </div>
              <span style={{ fontWeight: 500, fontSize: "0.9rem" }}>{p.label}</span>
              <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: p.color }}>
                {selected ? "Selected" : "Click to add"}
              </span>
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
            background: selectedProviders.length > 0 ? "#2563eb" : "#9ca3af",
            color: "#fff",
            fontWeight: 600,
            cursor: selectedProviders.length > 0 ? "pointer" : "default",
          }}
          disabled={selectedProviders.length === 0}
        >
          Next →
        </button>
      </div>
    </div>
  );
};
