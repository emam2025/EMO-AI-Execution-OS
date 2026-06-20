"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

interface Workspace {
  id: string;
  name: string;
  tenant_id: string;
  status: string;
}

interface Member {
  user_id: string;
  workspace_id: string;
  role: string;
}

export default function WorkspacePage() {
  const params = useParams();
  const workspaceId = params.id as string;
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    fetch(`/api/workspaces/${workspaceId}`)
      .then((res) => {
        if (!res.ok) throw new Error("Access denied or workspace not found");
        return res.json();
      })
      .then(setWorkspace)
      .catch((err) => setError(err.message));

    fetch(`/api/workspaces/${workspaceId}/members`)
      .then((res) => {
        if (!res.ok) return [];
        return res.json();
      })
      .then(setMembers)
      .catch(() => setMembers([]));
  }, [workspaceId]);

  if (error) {
    return (
      <div style={{ padding: "24px", fontFamily: "Inter, sans-serif" }}>
        <h1>Workspace Error</h1>
        <p style={{ color: "#dc2626" }}>{error}</p>
      </div>
    );
  }

  if (!workspace) {
    return (
      <div style={{ padding: "24px", fontFamily: "Inter, sans-serif" }}>
        <p>Loading workspace...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: "24px", fontFamily: "Inter, sans-serif" }}>
      <h1>{workspace.name}</h1>
      <p style={{ color: "#6b7280" }}>Tenant: {workspace.tenant_id}</p>
      <p style={{ color: "#6b7280" }}>Status: {workspace.status}</p>

      <h2 style={{ marginTop: "24px" }}>Members ({members.length})</h2>
      <ul>
        {members.map((m) => (
          <li key={m.user_id} style={{ padding: "4px 0" }}>
            {m.user_id} — {m.role}
          </li>
        ))}
      </ul>
    </div>
  );
}
