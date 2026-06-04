import React from "react";

export interface BetaUserRow {
  id: string;
  email: string;
  company: string;
  role: string;
  status: "PENDING" | "ACTIVE" | "SUSPENDED" | "REVOKED";
  lastActivity: number | null;
}

interface ActiveUsersGridProps {
  users: BetaUserRow[];
  onRevoke: (userId: string) => void;
  onSuspend: (userId: string) => void;
}

const statusColors: Record<string, string> = {
  ACTIVE: "#22c55e",
  PENDING: "#f59e0b",
  SUSPENDED: "#ef4444",
  REVOKED: "#6b7280",
};

function formatTime(ts: number | null): string {
  if (!ts) return "--";
  const diff = Date.now() - ts;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

export const ActiveUsersGrid: React.FC<ActiveUsersGridProps> = ({ users, onRevoke, onSuspend }) => (
  <div className="glass-panel" style={{ padding: 16 }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
      <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Active Beta Users</h3>
      <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>{users.length} registered</span>
    </div>
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
            <th style={{ textAlign: "left", padding: "8px 4px", fontWeight: 500, color: "#6b7280" }}>Email</th>
            <th style={{ textAlign: "left", padding: "8px 4px", fontWeight: 500, color: "#6b7280" }}>Company</th>
            <th style={{ textAlign: "left", padding: "8px 4px", fontWeight: 500, color: "#6b7280" }}>Role</th>
            <th style={{ textAlign: "left", padding: "8px 4px", fontWeight: 500, color: "#6b7280" }}>Status</th>
            <th style={{ textAlign: "left", padding: "8px 4px", fontWeight: 500, color: "#6b7280" }}>Last Activity</th>
            <th style={{ textAlign: "right", padding: "8px 4px", fontWeight: 500, color: "#6b7280" }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.length === 0 ? (
            <tr>
              <td colSpan={6} style={{ textAlign: "center", padding: 24, color: "#9ca3af" }}>No users registered</td>
            </tr>
          ) : (
            users.map((user) => (
              <tr key={user.id} style={{ borderBottom: "1px solid rgba(0,0,0,0.04)" }}>
                <td style={{ padding: "8px 4px" }}>{user.email}</td>
                <td style={{ padding: "8px 4px" }}>{user.company}</td>
                <td style={{ padding: "8px 4px" }}>{user.role}</td>
                <td style={{ padding: "8px 4px" }}>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "2px 8px",
                      borderRadius: 10,
                      fontSize: "0.7rem",
                      fontWeight: 600,
                      background: statusColors[user.status] || "#6b7280",
                      color: "#fff",
                    }}
                  >
                    {user.status}
                  </span>
                </td>
                <td style={{ padding: "8px 4px", color: "#6b7280" }}>{formatTime(user.lastActivity)}</td>
                <td style={{ padding: "8px 4px", textAlign: "right" }}>
                  {user.status === "ACTIVE" && (
                    <button
                      onClick={() => onSuspend(user.id)}
                      style={{
                        padding: "2px 8px",
                        fontSize: "0.7rem",
                        border: "1px solid #f59e0b",
                        borderRadius: 4,
                        background: "transparent",
                        color: "#f59e0b",
                        cursor: "pointer",
                        marginRight: 4,
                      }}
                    >
                      Suspend
                    </button>
                  )}
                  {(user.status === "ACTIVE" || user.status === "SUSPENDED") && (
                    <button
                      onClick={() => onRevoke(user.id)}
                      style={{
                        padding: "2px 8px",
                        fontSize: "0.7rem",
                        border: "1px solid #ef4444",
                        borderRadius: 4,
                        background: "transparent",
                        color: "#ef4444",
                        cursor: "pointer",
                      }}
                    >
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  </div>
);
