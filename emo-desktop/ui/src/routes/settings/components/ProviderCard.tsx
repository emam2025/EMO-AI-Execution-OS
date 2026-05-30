import React, { useState, useCallback } from "react";
import { KeyInputMask } from "./KeyInputMask";
import { ConnectionTestIndicator } from "./ConnectionTestIndicator";
import type { ProviderId, ProviderStatus, ProviderConfig } from "../../../../lib/credentials/types";

interface ProviderCardProps {
  config: ProviderConfig;
  status: ProviderStatus;
  hasKey: boolean;
  onSave: (key: string) => Promise<void>;
  onTest: () => Promise<boolean>;
  onRotate: (newKey: string) => Promise<void>;
  onDelete: () => Promise<void>;
}

const STATUS_LABELS: Record<ProviderStatus, { label: string; color: string }> = {
  active: { label: "Active", color: "text-green-600 bg-green-50" },
  rate_limited: { label: "Rate Limited", color: "text-amber-600 bg-amber-50" },
  invalid_key: { label: "Invalid Key", color: "text-red-600 bg-red-50" },
  not_configured: { label: "Not Configured", color: "text-gray-400 bg-gray-50" },
};

export const ProviderCard: React.FC<ProviderCardProps> = ({
  config,
  status,
  hasKey,
  onSave,
  onTest,
  onRotate,
  onDelete,
}) => {
  const [keyInput, setKeyInput] = useState("");
  const [testState, setTestState] = useState<"idle" | "testing" | "success" | "failure">("idle");
  const [testError, setTestError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isRotating, setIsRotating] = useState(false);

  const statusInfo = STATUS_LABELS[status] ?? STATUS_LABELS.not_configured;

  const handleSave = useCallback(async () => {
    if (!keyInput.trim()) return;
    setIsSaving(true);
    try {
      await onSave(keyInput.trim());
      setKeyInput("");
    } finally {
      setIsSaving(false);
    }
  }, [keyInput, onSave]);

  const handleTest = useCallback(async () => {
    setTestState("testing");
    setTestError("");
    try {
      const ok = await onTest();
      setTestState(ok ? "success" : "failure");
      if (!ok) setTestError("Connection failed");
    } catch (e) {
      setTestState("failure");
      setTestError(String(e));
    }
  }, [onTest]);

  const handleRotate = useCallback(async () => {
    if (!keyInput.trim()) return;
    setIsRotating(true);
    try {
      await onRotate(keyInput.trim());
      setKeyInput("");
    } finally {
      setIsRotating(false);
    }
  }, [keyInput, onRotate]);

  const handleDelete = useCallback(async () => {
    if (!window.confirm(`Delete ${config.label} API key?`)) return;
    await onDelete();
  }, [config.label, onDelete]);

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-base">{config.label}</h3>
          <p className="text-xs text-gray-400 font-mono">{config.id}</p>
        </div>
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusInfo.color}`}>
          {statusInfo.label}
        </span>
      </div>

      <KeyInputMask
        providerId={config.id}
        value={keyInput}
        onChange={setKeyInput}
        disabled={isSaving || isRotating}
      />

      {config.requiresBaseUrl && (
        <p className="text-xs text-gray-400">
          Requires custom base URL — configure in runtime settings.
        </p>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={handleSave}
          disabled={!keyInput.trim() || isSaving}
          className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 font-medium"
        >
          {isSaving ? "Saving..." : hasKey ? "Update Key" : "Save Key"}
        </button>

        {hasKey && (
          <>
            <button
              type="button"
              onClick={handleRotate}
              disabled={!keyInput.trim() || isRotating}
              className="px-3 py-1.5 text-sm rounded border border-amber-300 text-amber-700 hover:bg-amber-50 disabled:opacity-50 font-medium"
            >
              {isRotating ? "Rotating..." : "Rotate Key"}
            </button>
            <button
              type="button"
              onClick={handleDelete}
              className="px-3 py-1.5 text-sm rounded border border-red-200 text-red-600 hover:bg-red-50 font-medium"
            >
              Delete
            </button>
          </>
        )}

        <ConnectionTestIndicator
          state={testState}
          errorMessage={testError}
          onTest={handleTest}
          disabled={!hasKey}
        />
      </div>
    </div>
  );
};
