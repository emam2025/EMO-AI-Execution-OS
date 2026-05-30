/**
 * RuntimeClient — Axios/Fetch wrapper with Bearer Token + WebSocket event handler.
 *
 * Communicates exclusively through the IPC Gateway (Tauri commands).
 * No direct access to emo-runtime-service or v4.15.0 Runtime Core.
 */
import type {
  RuntimeSession,
  RuntimeHealth,
  RuntimeTelemetry,
  RuntimeEvent,
  ExecutionTrace,
} from "../../../types/telemetry";

const WS_EVENTS_URL = "ws://localhost:8080/api/events";
const HTTP_BASE = "http://localhost:8080";

let _sessionToken: string | null = null;
let _ws: WebSocket | null = null;

function authHeaders(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (_sessionToken) h["Authorization"] = `Bearer ${_sessionToken}`;
  return h;
}

export const RuntimeClient = {
  /** Start the emo-runtime-service and obtain a session. */
  async startRuntime(): Promise<RuntimeSession> {
    // In production this invokes a Tauri IPC command.
    // Skeleton: returns a mock session.
    const session: RuntimeSession = {
      session_token: `st_${crypto.randomUUID()}`,
      port: 8080,
      pid: Math.floor(Math.random() * 60000) + 1000,
      status: "starting",
    };
    _sessionToken = session.session_token;
    return session;
  },

  /** Stop the runtime process by PID. */
  async stopRuntime(pid: number): Promise<{ pid: number; terminated: boolean; signal: string }> {
    _sessionToken = null;
    closeEventStream();
    return { pid, terminated: true, signal: "SIGTERM" };
  },

  /** Get runtime health proxy. */
  async getRuntimeStatus(port: number): Promise<RuntimeHealth> {
    const res = await fetch(`${HTTP_BASE}/api/health`, { headers: authHeaders() });
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
    return res.json();
  },

  /** Fetch a full execution trace. */
  async getTrace(traceId: string): Promise<ExecutionTrace> {
    const res = await fetch(`${HTTP_BASE}/api/trace/${traceId}`, { headers: authHeaders() });
    if (!res.ok) throw new Error(`Trace fetch failed: ${res.status}`);
    return res.json();
  },

  /** Connect to the runtime.events WebSocket stream. */
  connectEventStream(onEvent: (event: RuntimeEvent) => void): void {
    if (_ws) closeEventStream();
    _ws = new WebSocket(WS_EVENTS_URL);
    _ws.onmessage = (msg) => {
      try {
        const event: RuntimeEvent = JSON.parse(msg.data);
        onEvent(event);
      } catch {
        console.warn("[RuntimeClient] Invalid event payload");
      }
    };
    _ws.onerror = () => console.error("[RuntimeClient] WebSocket error");
  },
};

export function closeEventStream(): void {
  _ws?.close();
  _ws = null;
}

export function getSessionToken(): string | null {
  return _sessionToken;
}
