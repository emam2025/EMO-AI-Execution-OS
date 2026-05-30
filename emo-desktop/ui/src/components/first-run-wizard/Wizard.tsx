import React, { useState } from "react";
import { WelcomeStep } from "./WelcomeStep";
import { ConnectModelsStep } from "./ConnectModelsStep";
import { SelectModeStep } from "./SelectModeStep";
import { ValidateStep } from "./ValidateStep";
import { LaunchStep } from "./LaunchStep";

type Step = "welcome" | "connect-models" | "select-mode" | "validate" | "launch";

interface WizardProps {
  onComplete: () => void;
  onClose: () => void;
}

const STEP_ORDER: Step[] = ["welcome", "connect-models", "select-mode", "validate", "launch"];

const STEP_LABELS: Record<Step, string> = {
  welcome: "Welcome",
  "connect-models": "Connect Models",
  "select-mode": "Select Mode",
  validate: "Validate",
  launch: "Launch",
};

export const FirstRunWizard: React.FC<WizardProps> = ({ onComplete, onClose }) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const currentStep = STEP_ORDER[currentIndex];
  const [state, setState] = useState({
    providers: [] as string[],
    mode: "local" as "local" | "sandbox" | "enterprise",
    validationPassed: false,
  });

  const goNext = () => {
    if (currentIndex < STEP_ORDER.length - 1) {
      setCurrentIndex((i) => i + 1);
    }
  };

  const goBack = () => {
    if (currentIndex > 0) {
      setCurrentIndex((i) => i - 1);
    }
  };

  const handleLaunch = () => {
    // Persist completion
    localStorage.setItem("emo-first-run-completed", "true");
    localStorage.setItem("emo-first-run-state", JSON.stringify(state));
    onComplete();
  };

  const isFirst = currentIndex === 0;
  const isLast = currentIndex === STEP_ORDER.length - 1;

  const renderStep = () => {
    switch (currentStep) {
      case "welcome":
        return <WelcomeStep onNext={goNext} />;
      case "connect-models":
        return (
          <ConnectModelsStep
            selectedProviders={state.providers}
            onSelect={(providers) => setState((s) => ({ ...s, providers }))}
            onNext={goNext}
            onBack={goBack}
          />
        );
      case "select-mode":
        return (
          <SelectModeStep
            selected={state.mode}
            onSelect={(mode) => setState((s) => ({ ...s, mode }))}
            onNext={goNext}
            onBack={goBack}
          />
        );
      case "validate":
        return (
          <ValidateStep
            providers={state.providers}
            mode={state.mode}
            onValidationResult={(passed) => setState((s) => ({ ...s, validationPassed: passed }))}
            onNext={goNext}
            onBack={goBack}
          />
        );
      case "launch":
        return (
          <LaunchStep
            providers={state.providers}
            mode={state.mode}
            validationPassed={state.validationPassed}
            onLaunch={handleLaunch}
            onBack={goBack}
          />
        );
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9998,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.4)",
        backdropFilter: "blur(8px)",
      }}
    >
      <div
        className="glass-panel"
        style={{
          width: 560,
          maxHeight: "80vh",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          animation: "smooth-scale-in 0.2s ease-out",
        }}
      >
        {/* Progress bar */}
        <div style={{ padding: "16px 24px 0", display: "flex", gap: 6 }}>
          {STEP_ORDER.map((step, i) => (
            <div
              key={step}
              style={{
                flex: 1,
                height: 3,
                borderRadius: 2,
                background: i <= currentIndex ? "#3b82f6" : "rgba(0,0,0,0.08)",
                transition: "background 0.3s",
              }}
            />
          ))}
        </div>

        {/* Step label */}
        <div style={{ padding: "12px 24px 0", fontSize: "0.7rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "#9ca3af" }}>
          Step {currentIndex + 1} of {STEP_ORDER.length} — {STEP_LABELS[currentStep]}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: "auto", padding: "16px 24px" }}>
          {renderStep()}
        </div>
      </div>
    </div>
  );
};
