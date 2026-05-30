/**
 * Tauri IPC Commands — Runtime Bridge
 *
 * These commands are invoked by the Tauri backend (Rust) and forwarded to
 * the emo-runtime-service (Python process launcher/proxy).
 *
 * Skeleton only — no actual process management in Phase P1.
 * Production implementation will spawn `emo-runtime-service` binary.
 */
import { invoke } from "@tauri-apps/api/core";
import type {
  RuntimeSession,
  RuntimeHealth,
  ExecutionTrace,
} from "../../../ui/types/telemetry";

/**
 * Start the emo-runtime-service process.
 * Returns a unique session token, assigned port, and PID.
 */
export async function startRuntime(): Promise<RuntimeSession> {
  return invoke<RuntimeSession>("start_runtime");
}

/**
 * Gracefully stop the runtime process by PID.
 * SIGTERM → 5s wait → SIGKILL if still alive.
 */
export async function stopRuntime(pid: number): Promise<{
  pid: number;
  terminated: boolean;
  signal: string;
}> {
  return invoke("stop_runtime", { pid });
}

/**
 * Get runtime health via emo-runtime-service proxy.
 */
export async function getRuntimeStatus(
  port: number,
  token: string
): Promise<RuntimeHealth> {
  return invoke<RuntimeHealth>("get_runtime_status", { port, token });
}

/**
 * Open a WebSocket/SSE stream to runtime.events.
 * If traceId is provided, filter events to that trace only.
 */
export async function streamEvents(
  traceId?: string
): Promise<{ streamId: string; type: "websocket" | "sse" }> {
  return invoke("stream_events", { traceId });
}

/**
 * Fetch a full execution trace from GET /trace/{trace_id}.
 */
export async function getTrace(
  traceId: string,
  token: string
): Promise<ExecutionTrace> {
  return invoke<ExecutionTrace>("get_trace", { traceId, token });
}
