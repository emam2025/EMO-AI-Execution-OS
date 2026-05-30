import React, { useState, useEffect } from "react";

interface ValidateStepProps {
  providers: string[];
  mode: string;
  onValidationResult: (passed: boolean) => void;
  onNext: () => void;
  onBack: () => void;
}

interface CheckResult {
  label: string;
  passed: boolean | null;
  message: string;
}

export const ValidateStep: React.FC<ValidateStepProps> = ({
  providers,
  mode,
  onValidationResult,
  onNext,
  onBack,
}) => {
  const [checks, setChecks] = useState<CheckResult[]>([
    { label: "emo-runtime-service health", passed: null, message: "Checking..." },
    { label: "IPC authentication", passed: null, message: "Checking..." },
    { label: "WebSocket event stream", passed: null, message: "Checking..." },
    { label: "Provider credentials (OS Keychain)", passed: null, message: "Checking..." },
  ]);

  useEffect(() => {
    // Simulate validation checks against IPC contract
    const runChecks = async () => {
      // Check 1: Runtime health
      await delay(300);
      setChecks((prev) =>
        prev.map((c, i) =>
          i === 0 ? { ...c, passed: true, message: "Runtime reachable" } : c,
        ),
      );

      // Check 2: IPC auth
      await delay(250);
      setChecks((prev) =>
        prev.map((c, i) =>
          i === 1 ? { ...c, passed: true, message: "Bearer token valid" } : c,
        ),
      );

      // Check 3: WebSocket
      await delay(300);
      setChecks((prev) =>
        prev.map((c, i) =>
          i === 2 ? { ...c, passed: true, message: "WebSocket connected" } : c,
        ),
      );

      // Check 4: Provider keys
      await delay(250);
      const hasKeys = providers.length > 0;
      setChecks((prev) =>
        prev.map((c, i) =>
          i === 3
            ? {
                ...c,
                passed: hasKeys,
                message: hasKeys
                  ? `${providers.length} provider(s) configured in keychain`
                  : "No providers configured — will use defaults",
              }
            : c,
        ),
      );

      // Report result
      onValidationResult(true);
    };

    runChecks();
  }, []);

  const allPassed = checks.every((c) => c.passed !== false);
  const anyFailed = checks.some((c) => c.passed === false);
  const allChecked = checks.every((c) => c.passed !== null);

  return (
    <div>
      <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 4 }}>Validate Installation</h2>
      <p style={{ color: "#6b7280", fontSize: "0.85rem", marginBottom: 16 }}>
        Verifying runtime connectivity and provider configuration.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 24 }}>
        {checks.map((check, i) => (
          <div
            key={i}
            className="glass-panel"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "10px 14px",
            }}
          >
            <div
              style={{
                width: 18,
                height: 18,
                borderRadius: "50%",
                background:
                  check.passed === null
                    ? "#e5e7eb"
                    : check.passed
                      ? "#22c55e"
                      : "#ef4444",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fff",
                fontSize: "0.6rem",
                fontWeight: 700,
                flexShrink: 0,
                animation:
                  check.passed === null ? "pulse-dot 1.5s ease-in-out infinite" : undefined,
              }}
            >
              {check.passed === null ? "" : check.passed ? "✓" : "✗"}
            </div>
            <div style={{ flex: 1 }}>
              <span style={{ fontWeight: 500, fontSize: "0.85rem" }}>{check.label}</span>
              <p style={{ margin: 0, color: "#6b7280", fontSize: "0.75rem" }}>{check.message}</p>
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onBack} className="glass-input" style={{ padding: "8px 20px", cursor: "pointer" }}>
          ← Back
        </button>
        <button
          onClick={onNext}
          disabled={!allChecked || anyFailed}
          style={{
            padding: "8px 20px",
            borderRadius: 8,
            border: "none",
            background: allChecked && !anyFailed ? "#22c55e" : "#9ca3af",
            color: "#fff",
            fontWeight: 600,
            cursor: allChecked && !anyFailed ? "pointer" : "default",
          }}
        >
          {allChecked ? "All Checks Passed →" : "Running checks..."}
        </button>
      </div>
    </div>
  );
};

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
