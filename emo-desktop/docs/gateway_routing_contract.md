# Gateway Routing Contract — EMO Desktop Model Gateway

## Status

- **Version**: 1.0.0
- **Status**: DRAFT — Phase P3 (Gateway Routing Engine + Telemetry Integration)
- **Last Updated**: 2026-05-30

---

## Architecture

```
User Intent → IPC submit_request()
                  │
                  ▼
         GatewayRouter.selectRoute()
                  │
          ┌───────┴────────┐
          ▼                ▼
   RateLimitGuard    FailoverEngine
     tryConsume()     shouldFailover()
          │                │
          └───────┬────────┘
                  ▼
         emo-runtime-service
                  │
                  ▼
         Model Gateway (provider proxy)
                  │
          ┌───────┼───────┐
          ▼       ▼       ▼
        OpenAI  Anthropic  Groq
```

The routing layer is entirely client-side (Desktop TypeScript). It NEVER connects directly to AI providers — all traffic routes through `emo-runtime-service → Model Gateway`.

---

## Transition Matrix

### Normal Flow

| State | Trigger | Next State | Condition |
|-------|---------|-----------|-----------|
| Primary Active | Route request | Processing | provider status = "active" |
| Primary Active | Failover trigger | Fallback Selected | HTTP 429/5xx or timeout > 5s |
| Primary Active | Rate limit hit | Rate Limited | RPM exceeded for provider |
| Fallback Selected | Route request | Processing (fallback) | fallback provider status = "active" |
| Fallback Selected | All failovers exhausted | Error State | max_failover_attempts reached |
| Fallback Selected | Cooldown expired | Primary Active | cooldown_ms elapsed since failure |
| Rate Limited | Cooldown expired | Primary Active | cooldown_seconds elapsed |
| Error State | Manual or health check | Primary Active | provider health restored |

### Failover Chain Execution

```
Step 1: GatewayRouter.selectRoute() — picks optimal provider
Step 2: RateLimitGuard.tryConsume(provider) — checks RPM
Step 3: Request sent via IPC to emo-runtime-service
Step 4: On failure → FailoverEngine.shouldFailover() → detect trigger
Step 5: FailoverEngine.resolveNext() — walk chain for next alive provider
Step 6: Idempotency key (fk_*) generated for each failover hop
Step 7: notify_failover IPC event sent to runtime
Step 8: GatewayRouter.selectRoute() re-evaluated with updated health
```

---

## Security Bounds

### Hardened (IMMUTABLE)

1. **No hardcoded provider endpoints** — All provider URLs are resolved dynamically by the Model Gateway (emo-runtime-service). Desktop client only sends provider_id strings.
2. **No plaintext payloads in local logs** — The audit log (SQLite) stores only: request_id, provider_id, status_code, latency_ms, cost_estimate, failover_event. Request bodies and API keys are NEVER logged.
3. **No direct provider connections** — Desktop client never opens HTTP connections to OpenAI/Anthropic/etc. All traffic routes through emo-runtime-service → Model Gateway.
4. **Ephemeral keys only** — Provider API keys are injected via OS Keychain → ephemeral IPC (register_provider) and auto-cleared within 5 seconds.
5. **Idempotency enforcement** — Each failover hop carries a unique idempotency_key. The runtime MUST reject duplicate keys to prevent double processing.

### Restricted

6. **Rate limit enforcement** — RateLimitGuard blocks requests exceeding RPM at the client side. The block list is in-memory only (never persisted).
7. **Max failover attempts** — FailoverEngine stops after max_failover_attempts=3. All providers on cooldown = Error State.
8. **Cooldown** — Failed providers enter a 30-second cooldown. Health checks determine recovery.

---

## Audit Log Specification

### Storage

- **File**: `routing_decisions.db` (SQLite, local, encrypted at rest via Tauri safe storage)
- **Lifetime**: Created per session, deleted on session stop (`SIGTERM` handler)
- **Scope**: Only routing metadata — no request bodies, no API keys, no credentials

### Schema

```sql
CREATE TABLE routing_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    request_id TEXT NOT NULL UNIQUE,
    selected_provider TEXT NOT NULL,
    alternatives TEXT NOT NULL,         -- JSON array
    score REAL NOT NULL,
    reason TEXT NOT NULL,
    status_code INTEGER,                -- NULL if not yet processed
    latency_ms REAL NOT NULL DEFAULT 0,
    cost_estimate REAL NOT NULL DEFAULT 0,
    failover_event TEXT                 -- JSON, NULL if no failover
);
```

### Retention

- Audit log is ephemeral — deleted when session ends
- No archival or export of routing decisions
- In-memory buffer: last 1000 decisions

---

## Cost Tracking

| Metric | Source | Update Frequency |
|--------|--------|-----------------|
| cost_per_token | Runtime event payload | Per request |
| total_session_cost | TelemetryAggregator sum | Every 500ms |
| avg_latency_ms | TelemetryAggregator average | Every 500ms |
| failover_count | FailoverEngine counter | Per event |
| provider_success_rate | requests / failures ratio | Every 500ms |

Cost estimates are calculated client-side based on provider-reported token counts and pre-configured per-token rates. The emo-runtime-service is the source of truth for final billing.

---

## Error States and Recovery

| Error State | Trigger | Recovery |
|-------------|---------|----------|
| No active providers | All providers "down" | Manual reconfiguration or health check cycle |
| All failovers exhausted | 3 consecutive failover hops | Cooldown wait + backoff retry |
| Rate limit blocked | RPM exceeded + cooldown active | Wait for cooldown_seconds |
| Idempotency conflict | Duplicate idempotency_key | Runtime rejects and returns existing result |
| Audit log write failure | SQLite I/O error | Non-blocking warning, continue in memory |

---

## Future Compatibility

Per IPC Contract §Future Compatibility (v1.2.0):

1. New routing strategies MAY be added (e.g., random, round-robin, lowest-cost). Existing strategies SHALL NOT be removed.
2. New failover triggers MAY be added. Existing triggers SHALL NOT be removed.
3. New audit log fields MAY be added. Existing field types SHALL NOT change.
4. New cost tiers MAY be added. Existing tiers SHALL NOT be removed.
5. This contract version SHALL remain supported for at least 2 consecutive releases after deprecation notice.
6. Zero breaking changes to the RoutingDecision, FailoverEvent, or GatewayMetrics schemas without a major version bump.
