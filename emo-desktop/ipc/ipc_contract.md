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

- **Version**: 1.0.0
- **Status**: DRAFT — Phase P1
- **Last Updated**: 2026-05-29
