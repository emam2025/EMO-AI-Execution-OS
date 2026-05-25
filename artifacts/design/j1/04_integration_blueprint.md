# Phase J1 — Developer Experience Layer Integration Blueprint

## 1. Architecture Overview

The Developer Experience Layer sits on top of the F1 UnifiedRuntime API and
provides three external surfaces: **SDK** (programmatic), **CLI** (human-facing),
and **Documentation Portal** (reference). All three surfaces enforce a strict
one-way dependency: DevEx → F1 UnifiedRuntime → CompositionRoot → Core.

```
                    ┌──────────────────────────────────────────────────────────┐
                    │              Developer Experience Layer (J1)             │
                    │                                                          │
                    │  ┌────────────────┐  ┌──────────────┐  ┌──────────────┐  │
                    │  │  EMO SDK       │  │  EMO CLI     │  │  Documentation│  │
                    │  │  (ISDKClient)  │  │  (ICLIRuntime)│  │  Portal      │  │
                    │  └───────┬────────┘  └──────┬───────┘  └──────┬───────┘  │
                    │          │                   │                │          │
                    └──────────┼───────────────────┼────────────────┼──────────┘
                               │                   │                │
                    ┌──────────▼───────────────────▼────────────────▼──────────┐
                    │                    F1 UnifiedRuntime API                 │
                    │  submit / resume / cancel / observe / replay / scale     │
                    │  register_worker                                         │
                    └──────────────────────────┬───────────────────────────────┘
                                               │
                    ┌──────────────────────────▼───────────────────────────────┐
                    │                  CompositionRoot                         │
                    │  D8 Scheduler  │  D8 StateStore  │  D8 Dispatcher        │
                    │  I1/I2/I3 Infra  │  F4 Observability  │  ...             │
                    └──────────────────────────────────────────────────────────┘
```

### Key Principle

All external interactions with the Runtime MUST route through F1 UnifiedRuntime
API. The SDK and CLI are NEVER allowed to bypass F1 and access ExecutionEngine,
D8 services, I1/I2/I3 components, or F4 observability layers directly (LAW 13).

---

## 2. Data Flow Map

### Flow 1: SDK → F1 → DAG Submission

```
SDK Client                    F1 UnifiedRuntime              CompositionRoot
     │                              │                              │
     │  1. connect(endpoint,        │                              │
     │     auth_token,              │                              │
     │     devex_trace_id)          │                              │
     │─────────────────────────────>│                              │
     │                              │  2. validate auth_token     │
     │                              │     (RULE 3)                │
     │                              │  3. create session          │
     │  4. connection_result        │                              │
     │<─────────────────────────────│                              │
     │                              │                              │
     │  5. submit_dag(dag_spec,     │                              │
     │     context, options,        │                              │
     │     devex_trace_id)          │                              │
     │─────────────────────────────>│                              │
     │                              │  6. guard: submission guard │
     │                              │     (RULE 3)                │
     │                              │  7. publish                 │
     │                              │     runtime.execution.start │
     │                              │     ───────────────────────>│
     │                              │  8. delegate to             │
     │                              │     scheduler.schedule()    │
     │                              │     ───────────────────────>│
     │  9. ticket_id + status       │                              │
     │<─────────────────────────────│                              │
     │                              │                              │
     │  10. observe_execution(      │                              │
     │      ticket_id,              │                              │
     │      devex_trace_id)         │                              │
     │─────────────────────────────>│                              │
     │                              │  11. stream state via       │
     │      ◄──── state stream ─────│      F4 TraceCollector      │
     │      (async iterator)        │                              │
     │                              │                              │
     │  12. disconnect(session_id,  │                              │
     │      devex_trace_id)         │                              │
     │─────────────────────────────>│                              │
     │                              │  13. terminate session      │
     │  14. disconnect_confirm      │                              │
     │<─────────────────────────────│                              │
```

**LAW Compliance:**
- LAW 13: SDK always talks to F1 UnifiedRuntime — never to ExecutionEngine
- LAW 12: devex_trace_id flows through every step (1, 5, 10, 12)
- LAW 5: Submission published as `runtime.execution.start` event (step 7)
- RULE 3: Auth validation + submission guard pre-check (steps 2, 6)

### Flow 2: CLI → F1 / CodeGraph → Admin Operations

```
CLI                              F1 UnifiedRuntime         CodeGraph v1
 │                                       │                      │
 │  1. status(runtime_uri,               │                      │
 │     devex_trace_id)                   │                      │
 │──────────────────────────────────────>│                      │
 │                                       │  2. /health check    │
 │  3. status_result                     │                      │
 │<──────────────────────────────────────│                      │
 │                                       │                      │
 │  4. logs(trace_id="abc123",           │                      │
 │     tail=50, devex_trace_id)          │                      │
 │──────────────────────────────────────>│                      │
 │                                       │  5. query F4 logs    │
 │  6. log_entries                       │                      │
 │<──────────────────────────────────────│                      │
 │                                       │                      │
 │  7. replay(execution_id,              │                      │
 │     devex_trace_id)                   │                      │
 │──────────────────────────────────────>│                      │
 │                                       │  8. delegate to      │
 │                                       │     F1.replay()     │
 │  9. replay_ticket                     │                      │
 │<──────────────────────────────────────│                      │
 │                                       │                      │
 │  10. validate_architecture(           │                      │
 │      config_path,                     │                      │
 │      devex_trace_id)                  │                      │
 │──────────────────────────────────────────────────────────────>│
 │                                       │                      │
 │                                       │   11. read-only      │
 │                                       │       architecture   │
 │                                       │       query          │
 │  12. validation_result                │                      │
 │<──────────────────────────────────────────────────────────────│
```

**Routing Guard Matrix Applied:**
| Step | Command | Guard Decision | Reason |
|------|---------|---------------|--------|
| 1 | `status` | ALLOW → F1 | read-only, runtime required |
| 4 | `logs` | ALLOW → F1 | read-only, F4 via F1 |
| 7 | `replay` | ALLOW → F1 | F1-proxied, auth+traced |
| 10 | `validate` | ALLOW → CodeGraph | codegraph-only, read-only |
| N/A | `cancel` | BLOCK if !F1 | must route through F1 |

### Flow 3: CodeGraph → DocGenerator → Publication

```
CodeGraph v1               IDocGenerator            IAPISpecPublisher     Doc Portal
     │                          │                         │                   │
     │  1. snapshot_request     │                         │                   │
     │<─────────────────────────│                         │                   │
     │  2. codegraph_snapshot   │                         │                   │
     │──────────────────────────>│                         │                   │
     │                          │  3. G-D1: snapshot      │                   │
     │                          │     valid?              │                   │
     │                          │  4. extract structure   │                   │
     │                          │  5. G-D2: spec          │                   │
     │                          │     complete?            │                   │
     │                          │  6. load spec           │                   │
     │                          │────────────────────────>│                   │
     │                          │  7. runtime_spec        │                   │
     │                          │<────────────────────────│                   │
     │                          │  8. G-D3: canon 100%?   │                   │
     │                          │  9. render + hash       │                   │
     │                          │ 10. G-D4: det. doc?     │                   │
     │                          │ 11. publish_artifact    │                   │
     │                          │────────────────────────────────────────────>│
     │                          │                         │                   │
     │                          │                         │ 12. validate      │
     │                          │                         │     OpenAPI       │
     │                          │                         │ 13. publish       │
     │                          │                         │     async events  │
     │                          │                         │───────────────────>│
```

---

## 3. Correlation ID Strategy (devex_trace_id)

### Trace Hierarchy

Every J1 operation generates or receives a `devex_trace_id` that is propagated
across all downstream calls. The trace hierarchy follows:

```
devex_trace_id (J1 DevEx Layer)
├── sdk_trace_id     (ISDKClient — per-session)
│   ├── submission_id   (per-submit_dag)
│   └── observation_id  (per-observe_execution)
├── cli_trace_id     (ICLIRuntime — per-command)
│   ├── log_query_id     (per logs)
│   └── replay_id        (per replay)
├── doc_trace_id     (IDocGenerator — per-generation)
│   ├── extraction_id    (per extract_codegraph_structure)
│   ├── render_id        (per render_canon_laws)
│   └── publish_id       (per publish_artifact)
└── spec_trace_id    (IAPISpecPublisher — per-publish)
    ├── load_id           (per load_runtime_spec)
    ├── validate_id       (per validate_openapi_schema)
    └── rollback_id       (per rollback_spec)
```

### devex_trace_id Format

```
devex_trace_id = "dx_" + SHA-256(session_id + operation_type + timestamp_ns)[:24]
```

Where:
- `session_id`: SDK session or CLI invocation UUID
- `operation_type`: "sdk_submit", "cli_logs", "doc_generate", "spec_publish", etc.
- `timestamp_ns`: Current time in nanoseconds (ensures uniqueness)

### Propagation Rules

| Rule | Description | LAW |
|------|-------------|-----|
| **P-R1** | Every J1 protocol method accepts devex_trace_id as last parameter | LAW 12 |
| **P-R2** | Every response includes trace_id echoing the input devex_trace_id | LAW 12 |
| **P-R3** | devex_trace_id is propagated to F1 UnifiedRuntime as trace_id | LAW 12 |
| **P-R4** | devex_trace_id is propagated through EventBus to F4 observability | LAW 5 |
| **P-R5** | CLI logs query uses the original execution trace_id (not CLI's devex_trace_id) | LAW 12 |
| **P-R6** | Doc artifacts store devex_trace_id in metadata for back-traceability | LAW 12 |

---

## 4. Event Hook Definitions

The J1 layer publishes events to the EventBus for observability. All events use
the existing `ExecutionEvent` type with `event_type="STATE_TRANSITION"` and a
descriptive `action` in the payload.

### Hook Table

| # | Hook Name | Topic | Trigger | Payload Fields |
|---|-----------|-------|---------|----------------|
| H1 | `SDKConnected` | `runtime.devex.sdk.connected` | Successful SDK connect() | session_id, endpoint, devex_trace_id |
| H2 | `SDKDisconnected` | `runtime.devex.sdk.disconnected` | SDK disconnect() | session_id, duration_sec, devex_trace_id |
| H3 | `DAGSubmitted` | `runtime.devex.sdk.dag_submitted` | SDK submit_dag() | ticket_id, dag_hash, context, devex_trace_id |
| H4 | `CLICommandExecuted` | `runtime.devex.cli.command` | Any CLI command executed | command, subcommand, duration_ms, success, devex_trace_id |
| H5 | `CLICommandRejected` | `runtime.devex.cli.rejected` | CLI guard blocks command | command, subcommand, guard_checks, reason, devex_trace_id |
| H6 | `DocGenerationCompleted` | `runtime.devex.doc.generated` | Doc artifact generated | artifact_id, artifact_type, content_hash, source_ref, devex_trace_id |
| H7 | `DocPublished` | `runtime.devex.doc.published` | Artifact published to portal | artifact_id, target, publish_url, devex_trace_id |
| H8 | `SpecPublished` | `runtime.devex.spec.published` | API spec published | spec_id, format, endpoint_count, devex_trace_id |
| H9 | `SpecPublishFailed` | `runtime.devex.spec.publish_failed` | Spec validation failure | spec_id, errors, warnings, devex_trace_id |
| H10 | `SpecRolledBack` | `runtime.devex.spec.rolled_back` | Spec rolled back | spec_id, previous_hash, restored_endpoints, devex_trace_id |

### Event Schema (example)

```json
{
  "event_id": "dx_event_abc123",
  "event_type": "STATE_TRANSITION",
  "timestamp": 1712345678.123,
  "source": "ISDKClient",
  "payload": {
    "action": "SDKConnected",
    "session_id": "sess_xyz",
    "endpoint": "https://runtime.emo.ai/v1",
    "devex_trace_id": "dx_abcd1234efgh5678"
  },
  "trace_id": "dx_abcd1234efgh5678"
}
```

---

## 5. Integration Acceptance Criteria

| Criterion | Condition | Verification Method |
|-----------|-----------|-------------------|
| **Latency Budget** | SDK submit_dag: < 500ms p99 (excluding DAG execution). CLI logs: < 200ms p99. Doc generation: < 5s p99. Spec publish: < 2s p99. | Performance benchmarks |
| **Idempotency** | Same dag_spec + devex_trace_id -> same ticket_id (if previously submitted). Idempotency key = SHA-256(dag_spec + context + devex_trace_id). | Integration test: duplicate submission |
| **Determinism** | Same codegraph_snapshot + canon_version -> same doc artifact content_hash. Spec rollback restores exact previous content_hash. | DDG verification |
| **Zero Direct Runtime Access** | SDK MUST NOT import from core/runtime/infra/, core/runtime/reliability/, core/execution_engine.py, core/runtime/services/. CLI MUST NOT import from core/runtime/services/ or core/execution_core.py. | Import linting rule |
| **Trace Coverage** | Every SDK/CLI/Doc/Spec method must accept and return devex_trace_id. Every event hook must carry devex_trace_id. | Code review: 100% of protocol methods |
| **Guard Enforcement** | 100% of CLI commands evaluated against routing guards before execution. Guard G-R5 blocks if devex_trace_id is missing. | Integration test: CLI without trace_id |
| **Rollback Available** | Every published spec preserves previous_spec_hash for rollback. Rollback restores exact previous state. | Integration test: spec rollback |
| **Error Handling** | SDK connect failure returns structured error (not raw transport error). CLI logs failure returns partial results (not empty). Doc generation failure returns guard violation details. | Error response schema validation |
