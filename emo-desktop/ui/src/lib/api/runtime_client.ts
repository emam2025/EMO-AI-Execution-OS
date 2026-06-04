/**
 * RuntimeClient — Tauri IPC wrapper with MockAdapter for test isolation.
 *
 * Production: uses @tauri-apps/api/core invoke() for all operations.
 * Tests: uses MockAdapter to return controlled values without Tauri.
 *
 * CORE FREEZE: No imports from core/ or releases/
 */
import type { RuntimeSession, RuntimeHealth, RuntimeEvent } from "../../types/telemetry";
import type { ProviderId } from "../../../lib/credentials/types";

// ──────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────

export interface AgentTask {
  project_id: string;
  instruction: string;
}

export interface AgentResult {
  run_id: string;
  status: string;
  result: string;
  elapsed_seconds: number;
}

export interface RuntimeStatus {
  running: boolean;
  pid: number | null;
  port: number | null;
  healthy: boolean;
}

export interface RuntimeInfo {
  pid: number;
  port: number;
  status: string;
  session_token: string;
}

// ──────────────────────────────────────────────
// Mock adapter for test isolation
// ──────────────────────────────────────────────

export interface MockAdapter {
  startRuntime(): Promise<RuntimeInfo>;
  stopRuntime(pid: number): Promise<void>;
  getRuntimeStatus(): Promise<RuntimeStatus>;
  setApiKey(provider: ProviderId, key: string): Promise<void>;
  runAgent(task: AgentTask): Promise<AgentResult>;
}

let _mockAdapter: MockAdapter | null = null;

export function setMockAdapter(adapter: MockAdapter | null): void {
  _mockAdapter = adapter;
}

export function getMockAdapter(): MockAdapter | null {
  return _mockAdapter;
}

// ──────────────────────────────────────────────
// Session token management
// ──────────────────────────────────────────────

let _sessionToken: string | null = null;
let _runtimePort: number | null = null;
let _ws: WebSocket | null = null;

export function getSessionToken(): string | null {
  return _sessionToken;
}

export function closeEventStream(): void {
  _ws?.close();
  _ws = null;
}

// ──────────────────────────────────────────────
// Production: Tauri IPC invoke
// ──────────────────────────────────────────────

async function tauriInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<T>(cmd, args);
  } catch {
    throw new Error(`IPC invoke failed: ${cmd} — Tauri backend unavailable`);
  }
}

// ──────────────────────────────────────────────
// RuntimeClient
// ──────────────────────────────────────────────

export const RuntimeClient = {
  async startRuntime(): Promise<RuntimeSession> {
    if (_mockAdapter) {
      const info = await _mockAdapter.startRuntime();
      _sessionToken = info.session_token;
      _runtimePort = info.port;
      return {
        session_token: info.session_token,
        port: info.port,
        pid: info.pid,
        status: info.status,
      } as RuntimeSession;
    }

    const info = await tauriInvoke<RuntimeInfo>("start_runtime");
    _sessionToken = info.session_token;
    _runtimePort = info.port;
    return {
      session_token: info.session_token,
      port: info.port,
      pid: info.pid,
      status: info.status,
    } as RuntimeSession;
  },

  async stopRuntime(pid: number): Promise<{ pid: number; terminated: boolean; signal: string }> {
    if (_mockAdapter) {
      await _mockAdapter.stopRuntime(pid);
      _sessionToken = null;
      _runtimePort = null;
      closeEventStream();
      return { pid, terminated: true, signal: "SIGTERM" };
    }

    await tauriInvoke<void>("stop_runtime", { pid });
    _sessionToken = null;
    _runtimePort = null;
    closeEventStream();
    return { pid, terminated: true, signal: "SIGTERM" };
  },

  async getRuntimeStatus(): Promise<RuntimeHealth> {
    if (_mockAdapter) {
      const status = await _mockAdapter.getRuntimeStatus();
      return { status: status.running ? "running" : "stopped" } as RuntimeHealth;
    }

    const status = await tauriInvoke<RuntimeStatus>("get_runtime_status");
    return { status: status.running ? "running" : "stopped" } as RuntimeHealth;
  },

  async setApiKey(provider: ProviderId, key: string): Promise<void> {
    if (_mockAdapter) {
      return _mockAdapter.setApiKey(provider, key);
    }
    await tauriInvoke<void>("set_api_key", { provider, key });
  },

  async runAgent(task: AgentTask): Promise<AgentResult> {
    if (_mockAdapter) {
      return _mockAdapter.runAgent(task);
    }
    return tauriInvoke<AgentResult>("run_agent", { task });
  },

  connectEventStream(onEvent: (event: RuntimeEvent) => void): void {
    if (_ws) closeEventStream();
    const port = _runtimePort ?? 8080;
    _ws = new WebSocket(`ws://localhost:${port}/api/events`);
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
