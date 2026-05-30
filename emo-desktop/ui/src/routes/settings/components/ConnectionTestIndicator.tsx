import React from "react";

type TestState = "idle" | "testing" | "success" | "failure";

interface ConnectionTestIndicatorProps {
  state: TestState;
  errorMessage?: string;
  onTest: () => void;
  disabled?: boolean;
}

export const ConnectionTestIndicator: React.FC<ConnectionTestIndicatorProps> = ({
  state,
  errorMessage,
  onTest,
  disabled = false,
}) => {
  const colorMap: Record<TestState, string> = {
    idle: "bg-gray-100 text-gray-600 border-gray-300",
    testing: "bg-blue-50 text-blue-600 border-blue-300 animate-pulse",
    success: "bg-green-50 text-green-700 border-green-300",
    failure: "bg-red-50 text-red-700 border-red-300",
  };

  const labelMap: Record<TestState, string> = {
    idle: "Test Connection",
    testing: "Testing...",
    success: "Connected ✓",
    failure: "Failed ✗",
  };

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={onTest}
        disabled={disabled || state === "testing"}
        className={`px-3 py-1.5 text-sm rounded border font-medium transition-colors ${colorMap[state]}`}
      >
        {labelMap[state]}
      </button>
      {state === "failure" && errorMessage && (
        <span className="text-xs text-red-500 max-w-xs truncate">
          {errorMessage}
        </span>
      )}
    </div>
  );
};
