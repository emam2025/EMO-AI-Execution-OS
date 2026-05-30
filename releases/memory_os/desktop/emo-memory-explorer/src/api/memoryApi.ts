const API_BASE = "http://localhost:3001/api";

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...opts?.headers },
    ...opts,
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  getStats: () => request<{ entries: number; nodes: number; edges: number }>("/stats"),
  getSpaces: (tenantId: string) =>
    request<{ spaces: Array<{ id: string; type: string; name: string }> }>(`/spaces?tenant=${tenantId}`),
  getAuditLog: (tenantId: string, limit = 50) =>
    request<{ entries: Array<Record<string, unknown>> }>(`/audit?tenant=${tenantId}&limit=${limit}`),
  getRetention: (tenantId: string, projectId: string) =>
    request<Record<string, unknown>>(`/retention?tenant=${tenantId}&project=${projectId}`),
  setRetention: (tenantId: string, projectId: string, config: Record<string, unknown>) =>
    request("/retention", {
      method: "PUT",
      body: JSON.stringify({ tenantId, projectId, ...config }),
    }),
  runRetention: (tenantId: string, projectId: string, dryRun = true) =>
    request("/retention/run", {
      method: "POST",
      body: JSON.stringify({ tenantId, projectId, dryRun }),
    }),
};
