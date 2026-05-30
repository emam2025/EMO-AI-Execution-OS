import React, { useState } from "react";

interface KeyInputMaskProps {
  /** The provider ID (used for labeling). */
  providerId: string;
  /** Current key value (masked). */
  value: string;
  /** Called when the user edits the key. */
  onChange: (value: string) => void;
  /** Disabled state while testing / saving. */
  disabled?: boolean;
}

/**
 * Secure key input with masking, reveal toggle, and paste protection
 * against accidental exposure. NEVER logs the key value to console.
 */
export const KeyInputMask: React.FC<KeyInputMaskProps> = ({
  providerId,
  value,
  onChange,
  disabled = false,
}) => {
  const [isRevealed, setIsRevealed] = useState(false);

  const handlePaste = (e: React.ClipboardEvent) => {
    // Prevent paste into non-masked elements; allow paste into the field.
    // The value goes directly to onChange, not to any log.
    e.stopPropagation();
  };

  return (
    <div className="flex items-center gap-2">
      <input
        type={isRevealed ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onPaste={handlePaste}
        disabled={disabled}
        placeholder={
          value
            ? "••••••••••••••••"
            : `Enter ${providerId} API key...`
        }
        className="flex-1 p-2 border rounded font-mono text-sm"
        autoComplete="off"
        spellCheck={false}
        data-lpignore="true"
      />
      <button
        type="button"
        onClick={() => setIsRevealed(!isRevealed)}
        className="p-2 text-gray-500 hover:text-gray-700 text-sm"
        aria-label={isRevealed ? "Hide key" : "Show key"}
        tabIndex={-1}
      >
        {isRevealed ? "🙈" : "👁"}
      </button>
      {value && (
        <span className="text-xs text-green-600 whitespace-nowrap">
          {isRevealed ? "visible" : "masked"}
        </span>
      )}
    </div>
  );
};
