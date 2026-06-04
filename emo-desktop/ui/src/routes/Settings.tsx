import React from "react";
import { useRuntimeStore } from "../stores/runtime";

export const Settings: React.FC = () => {
  const { session, isConnected } = useRuntimeStore();

  return (
    <div style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>
          Settings
        </h1>
        <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "#6b7280" }}>
          Connection, session, and system details
        </p>
      </div>

      <div className="glass-panel" style={{ padding: 16 }}>
        <div className="section-header">Connection</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="metric-card" style={{ padding: 10 }}>
            <span className="metric-card-label">Status</span>
            <span
              className={`status-badge ${isConnected ? "status-badge-active" : "status-badge-down"}`}
              style={{ marginLeft: 8 }}
            >
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
          <div className="metric-card" style={{ padding: 10 }}>
            <span className="metric-card-label">Host</span>
            <span style={{ marginLeft: 8, fontFamily: "monospace", fontSize: "0.85rem" }}>localhost</span>
          </div>
          <div className="metric-card" style={{ padding: 10 }}>
            <span className="metric-card-label">Port</span>
            <span style={{ marginLeft: 8, fontFamily: "monospace", fontSize: "0.85rem" }}>8080</span>
          </div>
          {session && (
            <div className="metric-card" style={{ padding: 10 }}>
              <span className="metric-card-label">Session</span>
              <span style={{ marginLeft: 8, fontFamily: "monospace", fontSize: "0.75rem", color: "#6b7280" }}>
                {session.session_token?.slice(0, 20)}…
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="glass-panel" style={{ padding: 16 }}>
        <div className="section-header">Authentication</div>
        <p style={{ fontSize: "0.85rem", color: "#6b7280", margin: "8px 0 0" }}>
          Session managed by the application. Re-authenticate by restarting.
          Governance layer (RBAC, audit trail, tenant isolation) is active for all system operations.
        </p>
        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          <span className="status-badge status-badge-active">RBAC: Active</span>
          <span className="status-badge status-badge-active">Audit: Active</span>
          <span className="status-badge status-badge-active">Tenant Isolation: Active</span>
        </div>
      </div>

      <div className="glass-panel" style={{ padding: 16 }}>
        <div className="section-header">About</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="metric-card" style={{ padding: 10 }}>
            <span className="metric-card-label">Desktop Version</span>
            <span style={{ marginLeft: 8, fontWeight: 600 }}>v0.1.4-product-alpha</span>
          </div>
          <div className="metric-card" style={{ padding: 10 }}>
            <span className="metric-card-label">Runtime</span>
            <span style={{ marginLeft: 8 }}>v4.15.0-delivery-ready (R1)</span>
          </div>
          <div className="metric-card" style={{ padding: 10 }}>
            <span className="metric-card-label">Governance</span>
            <span style={{ marginLeft: 8 }}>RBAC + Audit Trail + Tenant Isolation</span>
          </div>
          <div className="metric-card" style={{ padding: 10 }}>
            <span className="metric-card-label">Platform Support</span>
            <span style={{ marginLeft: 8 }}>macOS · Windows · Linux</span>
          </div>
        </div>
      </div>
    </div>
  );
};
