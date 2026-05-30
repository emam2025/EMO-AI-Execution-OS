import React from "react";
import { useMemoryStore, type RetentionConfig } from "../store/memoryStore";

const RetentionSettings: React.FC = () => {
  const retention = useMemoryStore((s) => s.retention);
  const setRetention = useMemoryStore((s) => s.setRetention);

  const update = (key: keyof RetentionConfig, value: string | number) => {
    setRetention({ ...retention, [key]: value });
  };

  return (
    <div style={{ maxWidth: 560 }}>
      <div style={{ marginBottom: 20, padding: 16, borderRadius: 8, background: "rgba(250,204,21,0.08)", border: "1px solid rgba(250,204,21,0.2)" }}>
        <div style={{ fontSize: "0.85rem", color: "#fbbf24", fontWeight: 600 }}>⚠ Governance Preview</div>
        <div style={{ fontSize: "0.8rem", color: "#a16207", marginTop: 4 }}>
          Retention policies apply on next governance run. Use dry-run mode to preview effects.
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {[
          { label: "Max Entries", key: "maxEntries" as const, type: "number", desc: "Soft cap before archival is triggered" },
          { label: "TTL (days)", key: "ttlDays" as const, type: "number", desc: "Maximum age before entry is eligible" },
          { label: "Archive After (days)", key: "archiveAfterDays" as const, type: "number", desc: "Entries older than this are archived" },
          { label: "Hard Delete After (days)", key: "hardDeleteAfterDays" as const, type: "number", desc: "Archived entries older than this are pruned" },
        ].map(({ label, key, type, desc }) => (
          <div key={key}>
            <label style={{ display: "block", fontSize: "0.85rem", color: "#e4e4e7", fontWeight: 500, marginBottom: 4 }}>
              {label}
            </label>
            <input
              type={type}
              value={retention[key]}
              onChange={(e) => update(key, type === "number" ? Number(e.target.value) : e.target.value)}
              style={{
                width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.1)",
                background: "rgba(255,255,255,0.05)", color: "#e4e4e7", fontSize: "0.85rem",
              }}
            />
            <div style={{ fontSize: "0.75rem", color: "#52525b", marginTop: 2 }}>{desc}</div>
          </div>
        ))}

        <div>
          <label style={{ display: "block", fontSize: "0.85rem", color: "#e4e4e7", fontWeight: 500, marginBottom: 4 }}>
            Exceed Action
          </label>
          <select
            value={retention.action}
            onChange={(e) => update("action", e.target.value as RetentionConfig["action"])}
            style={{
              width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(255,255,255,0.05)", color: "#e4e4e7", fontSize: "0.85rem",
            }}
          >
            <option value="archive">Archive</option>
            <option value="hard_delete">Hard Delete</option>
            <option value="warn">Warn Only</option>
          </select>
        </div>
      </div>

      <div style={{ marginTop: 24, display: "flex", gap: 12 }}>
        <button style={{
          padding: "10px 24px", borderRadius: 8, border: "none",
          background: "#a78bfa", color: "#fff", fontWeight: 600, fontSize: "0.85rem", cursor: "pointer",
        }}>
          Save Policy
        </button>
        <button style={{
          padding: "10px 24px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)",
          background: "transparent", color: "#a1a1aa", fontWeight: 500, fontSize: "0.85rem", cursor: "pointer",
        }}>
          Preview Dry Run
        </button>
      </div>
    </div>
  );
};

export default RetentionSettings;
