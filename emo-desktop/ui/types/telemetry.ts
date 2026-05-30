/**
 * RuntimeTelemetry — Unified telemetry schema for Runtime Monitor.
 *
 * This schema is the single source of truth for all runtime observability
 * data flowing from the emo-runtime-service to the EMO Desktop UI.
 *
 * Future Compatibility: New fields MAY be added. Clients MUST ignore unknown fields.
 */
export type RuntimeTelemetry = {
  /** CPU usage percentage (0-100) */
  cpu_usage: number;
  /** Memory usage in MB */
  memory_usage: number;
  /** Number of active agents (Planner, Critic, Optimizer, etc.) */
  active_agents: number;
  /** Number of tasks currently queued for execution */
  queued_tasks: number;
  /** Runtime uptime in seconds since last start_runtime() */
  uptime_seconds: number;
  /** Event bus latency in milliseconds */
  event_latency_ms: number;
};

/**
 * ExecutionTrace — Full execution trace from GET /trace/{trace_id}.
 */
export type ExecutionTrace = {
  trace_id: string;
  intent: string;
  tenant_id: string;
  events: TraceEvent[];
  valid: boolean;
};

export type TraceEvent = {
  timestamp: string;
  source: "planner" | "critic" | "optimizer" | "memory" | "runtime";
  event: string;
  data: Record<string, unknown>;
};

/**
 * RuntimeSession — Result from start_runtime() IPC command.
 */
export type RuntimeSession = {
  session_token: string;
  port: number;
  pid: number;
  status: "starting" | "running" | "stopped";
};

/**
 * RuntimeHealth — Result from get_runtime_status() IPC command.
 */
export type RuntimeHealth = {
  status: "ok" | "degraded" | "stopped";
  planner: boolean;
  critic: boolean;
  optimizer: boolean;
  state_machine: boolean;
  trace_correlator: boolean;
  uptime_seconds: number;
};

/**
 * RuntimeEvent — Single event from the runtime.events stream.
 */
export type RuntimeEvent = {
  type: "task_started" | "node_completed" | "agent_warning" | "runtime_error" | "trace_indexed";
  trace_id?: string;
  timestamp: string;
  payload: Record<string, unknown>;
};
