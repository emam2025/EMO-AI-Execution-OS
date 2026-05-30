# Gateway Specification — EMO Desktop IPC Gateway

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  EMO Desktop (Tauri)                 │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │   React   │  │   Zustand    │  │  Tauri Rust    │ │
│  │   (UI)    │──│   (Store)    │──│  (IPC Core)    │ │
│  └──────────┘  └──────────────┘  └───────┬────────┘ │
└──────────────────────────────────────────┼──────────┘
                                           │
                    IPC Commands (JSON-RPC) │
                                           ▼
                              ┌────────────────────────┐
                              │  emo-runtime-service   │
                              │  (Launcher / Proxy)    │
                              │                        │
                              │  ┌──────────────────┐  │
                              │  │  Process Manager  │  │
                              │  │  (start/stop/     │  │
                              │  │   health/ping)    │  │
                              │  └──────────────────┘  │
                              │  ┌──────────────────┐  │
                              │  │  REST Proxy       │  │
                              │  │  → /api/*         │  │
                              │  └──────────────────┘  │
                              │  ┌──────────────────┐  │
                              │  │  WS/SSE Bridge    │  │
                              │  │  → runtime.events │  │
                              │  └──────────────────┘  │
                              └──────────┬─────────────┘
                                         │
                              ┌──────────▼─────────────┐
                              │  v4.15.0 Runtime Core  │
                              │  (Python FastAPI)       │
                              └────────────────────────┘
```

## IPC Command Format

All IPC commands use Tauri's `invoke()` with JSON arguments. Responses are typed
(TypeScript interfaces defined in `ui/types/telemetry.ts`).

| Command | Arguments | Response Type |
|---|---|---|
| `start_runtime` | — | `RuntimeSession` |
| `stop_runtime` | `{ pid: number }` | `{ pid, terminated, signal }` |
| `get_runtime_status` | `{ port, token }` | `RuntimeHealth` |
| `stream_events` | `{ traceId?: string }` | `{ streamId, type }` |
| `get_trace` | `{ traceId, token }` | `ExecutionTrace` |

## Error Handling

IPC errors follow a standard format:
```json
{
  "code": "RUNTIME_NOT_STARTED",
  "message": "Runtime is not running. Call start_runtime() first.",
  "recoverable": true
}
```

### Error Codes
| Code | Meaning | Recoverable |
|---|---|---|
| `RUNTIME_NOT_STARTED` | No active session | Yes |
| `SESSION_EXPIRED` | Token invalidated by new session | Yes |
| `RUNTIME_CRASHED` | Process terminated unexpectedly | Yes |
| `TRACE_NOT_FOUND` | Trace ID not indexed | No |
| `INTERNAL_ERROR` | Unexpected IPC error | No |

## Security
- All IPC commands (except `start_runtime`) require `Bearer <session_token>`
- Session token is a UUIDv4 generated on `start_runtime()`
- Token invalidated on `stop_runtime()` or new `start_runtime()`
- No hardcoded secrets in the gateway

## Contract Version
- **Version**: 1.0.0
- **Status**: DRAFT — Phase P1
