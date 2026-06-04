import React, { useState } from "react";

export type ComplianceStandard = "SOC2" | "IEC62443" | "ISO27001";

export interface ReportPreview {
  standard: ComplianceStandard;
  score: number;
  passed: number;
  totalChecks: number;
  sections: { title: string; passed: boolean }[];
  generatedAt: string;
  verified: boolean;
}

interface ComplianceExportProps {
  onGenerate: (standard: ComplianceStandard) => ReportPreview | null;
  onExportPDF: (standard: ComplianceStandard) => void;
  onExportJSON: (standard: ComplianceStandard) => void;
}

const STANDARD_OPTIONS: { value: ComplianceStandard; label: string; color: string }[] = [
  { value: "SOC2", label: "SOC 2 Type II", color: "#3b82f6" },
  { value: "IEC62443", label: "IEC 62443", color: "#8b5cf6" },
  { value: "ISO27001", label: "ISO/IEC 27001", color: "#22c55e" },
];

export const ComplianceExport: React.FC<ComplianceExportProps> = ({ onGenerate, onExportPDF, onExportJSON }) => {
  const [selectedStandard, setSelectedStandard] = useState<ComplianceStandard | null>(null);
  const [preview, setPreview] = useState<ReportPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = () => {
    if (!selectedStandard) {
      setError("Select a compliance standard first");
      return;
    }
    setError(null);
    const result = onGenerate(selectedStandard);
    if (result) {
      setPreview(result);
    } else {
      setError("Failed to generate report");
    }
  };

  return (
    <div className="glass-panel" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(0,0,0,0.06)", fontWeight: 600, fontSize: "0.85rem" }}>
        Compliance Reports
      </div>
      <div style={{ padding: 12 }}>
        <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          {STANDARD_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => { setSelectedStandard(opt.value); setPreview(null); setError(null); }}
              style={{
                ...standardBtnStyle,
                borderColor: selectedStandard === opt.value ? opt.color : "rgba(0,0,0,0.1)",
                background: selectedStandard === opt.value ? opt.color : "#f3f4f6",
                color: selectedStandard === opt.value ? "white" : "#374151",
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <button onClick={handleGenerate} style={generateBtnStyle}>Generate Report</button>

        {error && (
          <div style={{ padding: "8px 12px", marginTop: 8, borderRadius: 6, background: "#fef2f2", color: "#ef4444", fontSize: "0.75rem" }}>
            {error}
          </div>
        )}

        {preview && (
          <div style={{ marginTop: 12, padding: 12, borderRadius: 8, border: "1px solid rgba(0,0,0,0.06)", background: "white" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.8rem" }}>{preview.standard} Report</div>
                <div style={{ fontSize: "0.7rem", color: "#9ca3af" }}>{new Date(preview.generatedAt).toLocaleString()}</div>
              </div>
              <div style={{
                width: 40, height: 40, borderRadius: "50%",
                background: `conic-gradient(${preview.score >= 0.7 ? "#22c55e" : "#ef4444"} ${preview.score * 100}%, #e5e7eb ${preview.score * 100}%)`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 700, fontSize: "0.75rem", color: preview.score >= 0.7 ? "#22c55e" : "#ef4444",
              }}>
                {(preview.score * 100).toFixed(0)}%
              </div>
            </div>

            <div style={{ fontSize: "0.7rem", color: "#6b7280", marginBottom: 8 }}>
              {preview.passed}/{preview.totalChecks} checks passed
              {preview.verified ? " · Audit trail verified" : " · Audit trail TAMPERED"}
            </div>

            <div style={{ marginBottom: 8 }}>
              {preview.sections.map((s, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 0", fontSize: "0.7rem" }}>
                  <span style={{ color: s.passed ? "#22c55e" : "#ef4444" }}>{s.passed ? "✓" : "✗"}</span>
                  <span>{s.title}</span>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={() => onExportPDF(selectedStandard!)} style={exportBtnStyle}>Export PDF</button>
              <button onClick={() => onExportJSON(selectedStandard!)} style={{ ...exportBtnStyle, background: "#1f2937", color: "white" }}>Export JSON</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const standardBtnStyle: React.CSSProperties = {
  padding: "6px 12px", fontSize: "0.7rem", border: "1px solid rgba(0,0,0,0.1)",
  borderRadius: 6, cursor: "pointer", fontWeight: 600, flex: 1,
};

const generateBtnStyle: React.CSSProperties = {
  padding: "8px 16px", fontSize: "0.75rem", border: "1px solid #3b82f6",
  borderRadius: 6, background: "#3b82f6", color: "white", cursor: "pointer",
  fontWeight: 600, width: "100%",
};

const exportBtnStyle: React.CSSProperties = {
  padding: "6px 12px", fontSize: "0.7rem", border: "1px solid rgba(0,0,0,0.1)",
  borderRadius: 4, background: "#f3f4f6", cursor: "pointer", fontWeight: 500, flex: 1,
};
