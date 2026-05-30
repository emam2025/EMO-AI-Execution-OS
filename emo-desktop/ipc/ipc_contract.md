# IPC Contract — EMO Desktop ←→ Runtime Communication Protocol

## Architecture

```
EMO Desktop (Tauri/React)
    │
    ├── IPC Gateway (Tauri Commands)
    │       │
    │       ├── emo-runtime-service (Launcher/Proxy)
    │       │       │
    │       │       └── v4.15.0 Runtime Core (Python FastAPI)
    │       │
    │       ├── WebSocket Client ←→ runtime.events (SSE/WS)
    │       │
    │       └── REST Client ←→ /api/* (HTTP)
```

The `emo-runtime-service` is a process abstraction layer that manages the Python runtime lifecycle.
The desktop NEVER calls `uvicorn` or `python main.py` directly — all launch/stop/health operations
route through this service.

---

## IPC Commands

### `start_runtime() -> RuntimeSession`

Launches the emo-runtime-service process.

**Returns:**
```json
{
  "session_token": "st_<uuid4>",
  "port": 8080,
  "pid": 12345,
  "status": "starting"
}
```

- `session_token`: unique per session (single-use; old token invalidated on new start)
- `port`: dynamically assigned or configured port
- `pid`: OS process ID of the emo-runtime-service

### `stop_runtime(pid: number) -> RuntimeShutdown`

Gracefully stops the runtime process.

**Protocol:**
1. Send SIGTERM to `pid`
2. Wait up to 5 seconds
3. If process still alive, send SIGKILL
4. Confirm termination

**Returns:**
```json
{ "pid": 12345, "terminated": true, "signal": "SIGTERM|SIGKILL" }
```

### `get_runtime_status(port: number, token: string) -> RuntimeHealth`

Proxies `/health` endpoint through the service.

**Returns:**
```json
{
  "status": "ok|degraded|stopped",
  "planner": true,
  "critic": true,
  "optimizer": true,
  "state_machine": true,
  "trace_correlator": true,
  "uptime_seconds": 3600
}
```

### `stream_events(trace_id?: string) -> EventSource`

Opens a WebSocket/SSE connection to `runtime.events` topic.

- Without `trace_id`: receives ALL runtime events (broadcast)
- With `trace_id`: receives events filtered to that trace only
- Events follow `runtime.events` schema (see `docs/event_stream_contract.md`)

### `get_trace(trace_id: string, token: string) -> ExecutionTrace`

Fetches full execution trace from `GET /trace/{trace_id}`.

**Returns:**
```json
{
  "trace_id": "og_<hex>",
  "intent": "summarize",
  "tenant_id": "acme",
  "events": [
    { "timestamp": "...", "source": "planner", "event": "plan_proposed", "data": {} }
  ],
  "valid": true
}
```

---

### `register_provider(provider_id: string, ephemeral_key: string) -> ProviderRegistrationResult`

Injects a provider API key ephemerally into the emo-runtime-service process.
The key is NEVER written to disk, env, or persistent storage — it is passed
via stdin or isolated env and cleared within 5 seconds.

**Ephemeral Injection Protocol:**
1. Desktop reads key from OS Keychain (the ONLY allowed source)
2. Desktop passes key to runtime via `register_provider` IPC command
3. Runtime receives key into isolated memory space (not written to any file)
4. Runtime confirms receipt → Desktop clears the key from its memory
5. Runtime auto-clears the key within 5 seconds or on session stop

**Parameters:**
```json
{
  "provider_id": "openai",
  "ephemeral_key": "sk-...",
  "method": "stdin"
}
```

**Returns:**
```json
{
  "provider_id": "openai",
  "injected": true,
  "method": "stdin",
  "cleared_at": 1717000000000
}
```

### `test_provider_connection(provider_id: string) -> ConnectionTestResult`

Sends a lightweight probe to the provider's API (e.g., `GET /v1/models`
or `/health`) through the Model Gateway and returns the result.

**Returns:**
```json
{
  "provider_id": "openai",
  "reachable": true,
  "status_code": 200,
  "latency_ms": 340,
  "model_count": 42
}
```

### `submit_request(routing_decision: RoutingDecision) -> SubmitResult`

Submits a user request to the optimal provider selected by the GatewayRouter.
The request is routed through emo-runtime-service → Model Gateway → provider.

**Parameters:**
```json
{
  "routing_decision": {
    "selected_provider": "openai",
    "alternatives": ["anthropic", "groq"],
    "score": 0.87,
    "reason": "Weighted score: latency=0.5, cost=0.5"
  },
  "intent": "summarize",
  "payload": { "text": "..." }
}
```

**Returns:**
```json
{
  "request_id": "rq_<uuid>",
  "provider": "openai",
  "status": "accepted",
  "estimated_cost_usd": 0.0023
}
```

### `notify_failover(trigger: FailoverTrigger) -> FailoverAck`

Notifies the runtime that a failover occurred. The runtime updates its
internal routing table and returns the new active route.

**Parameters:**
```json
{
  "provider_id": "openai",
  "trigger": "http_429",
  "idempotency_key": "fk_1717000000000_1_a1b2c3d4",
  "latency_ms": 3200
}
```

**Returns:**
```json
{
  "acknowledged": true,
  "new_active_route": "anthropic",
  "failover_count": 1
}
```

### `get_gateway_routing_status() -> GatewayRoutingStatus`

Returns the current state of the Model Gateway routing table, including
active routes, cost tracking, and failover readiness.

**Returns:**
```json
{
  "active_routes": ["openai", "anthropic"],
  "failover_ready": true,
  "cost_tracking": {
    "total_spent_usd": 12.45,
    "budget_limit_usd": 100.00
  },
  "routing_table": [
    { "provider": "openai", "priority": 1, "status": "active" },
    { "provider": "anthropic", "priority": 2, "status": "active" },
    { "provider": "groq", "priority": 3, "status": "rate_limited" }
  ]
}
```

---

## Authentication

All IPC commands (except `start_runtime`) require a valid `session_token` in the Authorization header:

```
Authorization: Bearer <session_token>
```

Token lifecycle:
- Generated on `start_runtime()`
- Invalidated on `stop_runtime()` or new `start_runtime()`
- Single active session at a time

---

## Future Compatibility Requirement (IMMUTABLE)

All IPC contracts, event schemas, fields, paths, and data types defined in this document
and all referenced contracts in `desktop/docs/` are designed for forward compatibility:

1. **No Breaking Fields**: New fields MAY be added to any response or event object. Clients
   MUST ignore unknown fields (permissive parsing).

2. **No Breaking Endpoints**: New paths MAY be added under `/api/*`. Existing paths SHALL
   NOT be removed or have their signatures changed.

3. **No Breaking Events**: New event types MAY be added to `runtime.events`. Existing event
   types SHALL NOT be removed or renamed. New fields MAY be added to existing event payloads.

4. **Schema Versioning**: All contracts carry a `version` field (semver). Major version bumps
   indicate breaking changes requiring coordinated migration.

5. **Minimum Compatibility Window**: A contract version SHALL remain supported for at least
   2 consecutive releases after deprecation notice.

6. **Scope**: This guarantee extends to all future product layers — Memory Explorer,
   Skill Graph Viewer, Cognitive OS Dashboard, and Enterprise OS Portal.

---

## Contract Version

- **Version**: 1.2.0
- **Status**: DRAFT — Phase P3 (Gateway Routing Engine + Telemetry Integration)
- **Last Updated**: 2026-05-30
