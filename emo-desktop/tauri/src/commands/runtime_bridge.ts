/**
 * Tauri IPC Commands — Runtime Bridge
 *
 * These commands are invoked by the Tauri backend (Rust) and forwarded to
 * the emo-runtime-service (Python process launcher/proxy).
 *
 * Skeleton only — no actual runtime execution in Phase P2.
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

// ── Phase P2: Credential Management ───────────────────

export type ProviderRegistrationResult = {
  provider_id: string;
  injected: boolean;
  method: "stdin" | "env_isolated";
  cleared_at: number | null;
};

export type ConnectionTestResult = {
  provider_id: string;
  reachable: boolean;
  status_code: number;
  latency_ms: number;
  model_count: number;
};

export type GatewayRoutingStatus = {
  active_routes: string[];
  failover_ready: boolean;
  cost_tracking: { total_spent_usd: number; budget_limit_usd: number };
  routing_table: Array<{
    provider: string;
    priority: number;
    status: "active" | "rate_limited" | "down";
  }>;
};

/**
 * Inject a provider API key ephemerally into the runtime process.
 * Key is passed via stdin or isolated env and cleared within 5 seconds.
 */
export async function registerProvider(
  providerId: string,
  ephemeralKey: string
): Promise<ProviderRegistrationResult> {
  return invoke<ProviderRegistrationResult>("register_provider", {
    providerId,
    ephemeralKey,
  });
}

/**
 * Test a provider connection through the Model Gateway.
 */
export async function testProviderConnection(
  providerId: string
): Promise<ConnectionTestResult> {
  return invoke<ConnectionTestResult>("test_provider_connection", { providerId });
}

/**
 * Get the Model Gateway routing status including failover readiness.
 */
export async function getGatewayRoutingStatus(): Promise<GatewayRoutingStatus> {
  return invoke<GatewayRoutingStatus>("get_gateway_routing_status");
}
