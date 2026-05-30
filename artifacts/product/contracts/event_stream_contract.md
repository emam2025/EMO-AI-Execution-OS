# Event Stream Contract — runtime.events

## Overview
The `runtime.events` stream carries all runtime observability events from the
emo-runtime-service to the EMO Desktop. Events are delivered via WebSocket or SSE.

## Transport

| Detail | Value |
|---|---|
| Protocol | WebSocket (primary) / SSE (fallback) |
| URL | `ws://<host>:<port>/api/events` |
| Authentication | Bearer token (session_token from `start_runtime()`) |
| Format | JSON lines (`\n` delimited) |

## Event Types

### `task_started`
Emitted when a new orchestration task begins execution.
```json
{
  "type": "task_started",
  "trace_id": "og_<hex>",
  "timestamp": "2026-05-29T00:00:00Z",
  "payload": {
    "intent": "summarize",
    "tenant_id": "acme",
    "plan_hash": "<sha256>"
  }
}
```

### `node_completed`
Emitted when a single DAG node finishes execution.
```json
{
  "type": "node_completed",
  "trace_id": "og_<hex>",
  "timestamp": "2026-05-29T00:00:01Z",
  "payload": {
    "node_id": "node_3",
    "status": "success",
    "duration_ms": 450
  }
}
```

### `agent_warning`
Emitted when an agent (Planner, Critic, Optimizer) produces a warning.
```json
{
  "type": "agent_warning",
  "trace_id": "og_<hex>",
  "timestamp": "2026-05-29T00:00:02Z",
  "payload": {
    "agent": "critic",
    "warning": "budget_exceeded",
    "message": "Estimated cost 150 exceeds limit 100"
  }
}
```

### `runtime_error`
Emitted on unrecoverable runtime errors.
```json
{
  "type": "runtime_error",
  "trace_id": null,
  "timestamp": "2026-05-29T00:00:03Z",
  "payload": {
    "error": "OrchestrationStateMachine: invalid transition",
    "severity": "critical"
  }
}
```

### `trace_indexed`
Emitted when a trace is fully indexed and available via `GET /trace/{id}`.
```json
{
  "type": "trace_indexed",
  "trace_id": "og_<hex>",
  "timestamp": "2026-05-29T00:00:04Z",
  "payload": {
    "event_count": 12,
    "duration_ms": 3200,
    "status": "completed"
  }
}
```

## Filtering
- Connect without query params: receives ALL events (broadcast)
- Connect with `?trace_id=og_<hex>`: receives events for that trace only
- Filtering is server-side; the client receives only matching events

## Future Compatibility
- New event types MAY be added without version bump
- New fields MAY be added to `payload` of existing event types
- Existing event types and fields SHALL NOT be removed or renamed
- Clients MUST ignore unknown event types and payload fields

## Contract Version
- **Version**: 1.0.0
- **Status**: DRAFT — Phase P1
