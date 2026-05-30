import React, { useState } from "react";

interface CreateProjectStepProps {
  onNext: (projectName: string) => void;
  onBack: () => void;
}

export const CreateProjectStep: React.FC<CreateProjectStepProps> = ({ onNext, onBack }) => {
  const [name, setName] = useState("");
  const [scope, setScope] = useState("personal");

  return (
    <div>
      <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 4 }}>Create Your First Project</h2>
      <p style={{ color: "#6b7280", fontSize: "0.85rem", marginBottom: 16 }}>
        Give your project a name and choose its scope.
      </p>

      <div style={{ marginBottom: 16 }}>
        <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "#374151", marginBottom: 6 }}>
          Project Name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. My First AI Project"
          className="glass-input"
          style={{ width: "100%", padding: "10px 12px" }}
          autoFocus
          onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) onNext(name.trim()); }}
        />
      </div>

      <div style={{ marginBottom: 24 }}>
        <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "#374151", marginBottom: 6 }}>
          Memory Scope
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          {["personal", "team", "enterprise"].map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              style={{
                flex: 1,
                padding: "10px 12px",
                borderRadius: 8,
                border: scope === s ? "2px solid #3b82f6" : "1px solid rgba(0,0,0,0.08)",
                background: scope === s ? "rgba(59,130,246,0.06)" : "rgba(255,255,255,0.5)",
                cursor: "pointer",
                fontWeight: scope === s ? 600 : 400,
                fontSize: "0.85rem",
                color: scope === s ? "#2563eb" : "#374151",
                transition: "all 0.12s ease-out",
              }}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onBack} className="glass-input" style={{ padding: "8px 20px", cursor: "pointer" }}>
          ← Back
        </button>
        <button
          onClick={() => { if (name.trim()) onNext(name.trim()); }}
          disabled={!name.trim()}
          style={{
            padding: "8px 20px",
            borderRadius: 8,
            border: "none",
            background: name.trim() ? "#2563eb" : "#9ca3af",
            color: "#fff",
            fontWeight: 600,
            cursor: name.trim() ? "pointer" : "not-allowed",
          }}
        >
          Next →
        </button>
      </div>
    </div>
  );
};
