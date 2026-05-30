# Phase H1 — Computer Use Runtime Integration Blueprint

## 1. Architecture Overview

The Computer Use Runtime (H1) sits between the G5 Multi-Agent Swarm and the
Phase 4 Sandbox, with observability flowing to F4.

```
G5.SwarmCoordinator ──> H1.BrowserRuntime ──> Phase4.Sandbox ──> ISessionJournal
G5.SwarmCoordinator ──> H1.DesktopWorker  ──> Phase4.Sandbox ──> ISessionJournal
G5.SwarmCoordinator ──> H1.VisionGrounding ──> Phase4.Sandbox ──> ISessionJournal
                                                      │
                                                      v
                                              F4.Observability
                                              (TraceCollector,
                                               TelemetryAggregator,
                                               AlertRouter)
```

**Key principle:** All computer use actions are dispatched through the G5 Swarm
(or a direct G5-managed agent), executed inside the Phase 4 Sandbox, recorded in
the Session Journal, and reported to F4 Observability.

---

## 2. Data Flow: G5 → H1 → Phase 4 Sandbox → F4

### Flow 1: Browser Automation (G5 → H1.BrowserRuntime)

```
G5.SwarmCoordinator
    │
    │  broadcast_task({
    │    "action": "navigate_to",
    │    "url": "https://example.com",
    │    "mission_trace_id": "msn_abc123"
    │  })
    ▼
H1.BrowserRuntime.launch_session(profile, isolation_context, capabilities)
    │
    │  ┌── Phase4.Sandbox ──────────────────────────┐
    │  │  sandbox_id: "sb_001"                      │
    │  │  network_policy: allowlist=[example.com]   │
    │  │  capability_guard: {can_navigate: True}     │
    │  │  isolation_token: "tok_abc"                │
    │  └────────────────────────────────────────────┘
    │
    ├── ISessionJournal.record_action(navigate_payload)
    │       └── journal_entry_id: "je_001"
    │
    ├── ISessionJournal.save_checkpoint(session_id)
    │       └── checkpoint_id: "ckpt_001"
    │
    └── F4.Observability
            ├── TraceCollector: record span {session_trace_id, "navigate", duration_ms}
            ├── TelemetryAggregator: {action_count, cpu_sec, memory_mb}
            └── AlertRouter: [if timeout] → alert "BROWSER_NAVIGATION_TIMEOUT"
```

### Flow 2: Desktop Interaction (G5 → H1.DesktopWorker)

```
G5.SwarmCoordinator
    │
    │  broadcast_task({
    │    "action": "click",
    │    "target": {"selector": "#submit-btn"},
    │    "mission_trace_id": "msn_def456"
    │  })
    ▼
H1.DesktopWorker.click(session_id, target, sandbox_token)
    │
    │  ┌── Phase4.Sandbox ──────────────────────────┐
    │  │  Interaction Guards I1 + I2 + I3           │
    │  │  Valid selector? ✅                         │
    │  │  Spatial bbox verified? ✅                  │
    │  │  Capability match? ✅                       │
    │  │  Sandbox token valid? ✅                    │
    │  └────────────────────────────────────────────┘
    │
    ├── IVisionGrounding.compute_spatial_bbox(element, viewport)
    │       └── absolute_bbox: [120, 340, 80, 32]
    │
    ├── ISessionJournal.record_action(click_payload)
    │
    └── F4.Observability
            ├── TraceCollector: {session_trace_id, "click", 45ms}
            └── AlertRouter: [if guard blocked] → alert "CAPABILITY_VIOLATION"
```

### Flow 3: Vision Grounding (G5 → H1.VisionGrounding)

```
G5.SwarmCoordinator
    │
    │  broadcast_task({
    │    "action": "detect_element",
    │    "query": {"text": "Submit", "role": "button"},
    │    "mission_trace_id": "msn_ghi789"
    │  })
    ▼
H1.VisionGrounding.detect_ui_element(image, query, sandbox_token)
    │
    │  ┌── Phase4.Sandbox ──────────────────────────┐
    │  │  Image: sandbox-scoped path                │
    │  │  Query: validated by IVisionGrounding      │
    │  │  Guard I5: visual consistency check        │
    │  │  Confidence ≥ 0.7? ✅ → return bbox        │
    │  └────────────────────────────────────────────┘
    │
    ├── ISessionJournal.record_action(detection_payload)
    │
    └── F4.Observability
            ├── TraceCollector: {session_trace_id, "detect_element", 120ms}
            └── TelemetryAggregator: {detection_count, avg_confidence}
```

---

## 3. Correlation ID Propagation (LAW 12)

Every computer use session and action carries a **session_trace_id** that flows
across all layers, enabling full back-traceability.

### ID Hierarchy

```
mission_trace_id (G5)
    └── session_trace_id (H1) — one per ComputerSession
            ├── action_sequence_number — one per ActionPayload
            ├── visual_context_hash — one per grounding operation
            ├── journal_entry_id — one per ISessionJournal.record_action
            ├── checkpoint_id — one per save_checkpoint
            └── replay_manifest_id — one per replay_to_state
```

### Propagation Matrix

| Layer | ID Carried | Format | Reference |
|-------|-----------|--------|-----------|
| G5 SwarmCoordinator | mission_trace_id | `msn_<hex>` | `SwarmContext.mission_trace_id` |
| H1 Session Manager | session_trace_id | `h1_<hex>` | `ComputerSession.session_trace_id` |
| H1 Action Dispatcher | session_trace_id + seq | `h1_<hex>:<seq>` | `ActionPayload.session_trace_id` |
| Phase 4 Sandbox | sandbox_trace_id | `sb_<hex>` | `SandboxProfile.isolation_token` |
| F4 TraceCollector | session_trace_id | `h1_<hex>` | `TraceCollector` span ID |
| F4 AlertRouter | session_trace_id | `h1_<hex>` | Alert payload |

### Generation Rule

```python
def generate_session_trace_id(mission_trace_id: str, session_index: int) -> str:
    raw = f"{mission_trace_id}:h1:{session_index}:{time.time_ns()}"
    return f"h1_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
```

---

## 4. Event Hooks for Drift & Failure Reporting

### SessionDrift Hook
**Triggered when:** State hash deviates from journal expectation during replay.

```yaml
hook: session_drift
payload:
  session_trace_id: "h1_abc123"
  mission_trace_id: "msn_abc123"
  expected_hash: "abc..."
  actual_hash:   "def..."
  deviation_pct: 0.03
  last_n_actions: 5
targets:
  - ISessionJournal.rollback_transaction()
  - F4.AlertRouter.alert({severity: "warning", type: "SESSION_DRIFT"})
```

### ActionTimeout Hook
**Triggered when:** Action duration exceeds allocated budget.

```yaml
hook: action_timeout
payload:
  session_trace_id: "h1_abc123"
  action_sequence: 42
  action_type: "navigate_to"
  timeout_sec: 30.0
  elapsed_sec: 35.2
targets:
  - F4.AlertRouter.alert({severity: "warning", type: "ACTION_TIMEOUT"})
  - H1.SessionJournal.record_action({error: "timeout"})
  - G5.SwarmCoordinator → escalation
```

### VisualGroundingFailure Hook
**Triggered when:** Vision grounding confidence < 0.7 or element not found.

```yaml
hook: visual_grounding_failure
payload:
  session_trace_id: "h1_abc123"
  mission_trace_id: "msn_abc123"
  query: {"text": "Submit", "role": "button"}
  confidence: 0.45
  fallback_method: "ocr"
targets:
  - H1.VisionGrounding.extract_text_ocr()  # fallback
  - F4.AlertRouter.alert({severity: "info", type: "GROUNDING_LOW_CONFIDENCE"})
```

### CapabilityViolation Hook
**Triggered when:** Guard I3 blocks an action due to missing capability.

```yaml
hook: capability_violation
payload:
  session_trace_id: "h1_abc123"
  mission_trace_id: "msn_abc123"
  action_type: "execute_script"
  missing_capability: "script_exec"
  sandbox_token_provided: "tok_x"
  sandbox_token_required: "tok_y"
targets:
  - F4.AlertRouter.alert({severity: "high", type: "CAPABILITY_VIOLATION"})
  - G5.SwarmCoordinator → terminate agent
  - H1.SessionJournal.record_action({error: "capability_violation"})
```

---

## 5. Acceptance Criteria

### Latency Budgets

| Operation | Budget | Action on Exceed |
|-----------|--------|-----------------|
| Navigation (page load) | 30s | Timeout, retry once, then fail |
| Script execution | 10s | Timeout, abort script |
| Click → response | 5s | Log warning, retry once |
| Type text (per 100 chars) | 2s | Log warning |
| Screenshot capture | 3s | Timeout, log error |
| UI element detection | 5s | Fallback to DOM selector |
| OCR text extraction | 5s | Timeout, return partial results |
| Template match | 3s | Timeout, return best-effort |
| Journal record_action | 500ms | Async fallback to buffer |
| Checkpoint save | 2s | Retry once, then log warning |

### Idempotency Guarantees

| Operation | Idempotent? | Mechanism |
|-----------|-------------|-----------|
| `navigate_to(url)` | ✅ | Same URL → same DOM hash (LAW 14) |
| `click(target, same coords)` | ✅ | Deterministic coordinate resolution |
| `type_text(input)` | ❌ | Each call appends — tracked by seq_number |
| `execute_script(code)` | ❌ | Side effects depend on DOM state |
| `screenshot_region(region)` | ✅ | Same region → same image hash (RULE 1) |
| `detect_ui_element(image, query)` | ✅ | Same image + query → same bbox (RULE 1) |
| `extract_text_ocr(image)` | ✅ | Same image → same text (RULE 1) |

### Determinism Thresholds

| Aspect | Threshold | Enforcement |
|--------|-----------|-------------|
| State hash deviation | 0% | Strict — chain must match |
| Visual diff (structural) | ≤2 elements | Warning, continue |
| Grounding confidence drop | ≤0.2 from original | Re-ground |
| Action duration variance | ±50% | Warning only |
| Replay determinism confidence | ≥0.95 | Abort if below |

### Rollback on Failure

| Failure Mode | Rollback Action | Journal Entry |
|-------------|----------------|---------------|
| Navigation timeout | Reset to previous DOM state | `checkpoint_restore` |
| Click missed target | Replay click with re-grounded coords | `action_retry` |
| Script execution error | No rollback (stateless) | `action_error` |
| Visual grounding miss | Retry with OCR fallback | `grounding_fallback` |
| Replay deviation | Rollback to last checkpoint | `rollback_transaction` |
| Capability violation | Terminate session | `session_terminated` |
| Sandbox breach | Terminate session + alert | `session_terminated` |

---

## 6. Compliance Mapping Summary

| Component | LAW/RULE | Evidence |
|-----------|----------|----------|
| IBrowserRuntime | LAW 2, 10, 14, 24; RULE 1, 2, 4 | §3.1 Flow 1, §2 Data Flow |
| IDesktopWorker | LAW 2, 10; RULE 1, 2, 3, 4 | §3.2 Flow 2, Interaction Guards I1–I3 |
| IVisionGrounding | LAW 2, 10; RULE 1, 3 | §3.3 Flow 3, Guard I5 |
| ISessionJournal | LAW 2, 10, 24; RULE 1, 3 | §4 Correlation IDs, I6, I8 |
| Session State Machine | LAW 10; RULE 2, 3, 4 | §3 State Machine, Guards I1–I8 |
| Phase 4 Sandbox integration | LAW 10; RULE 2, 4 | §2 all Flows, SandboxProfile model |
| F4 Observability hooks | LAW 12 | §4 Event Hooks, Correlation IDs |
| G5 Swarm integration | LAW 24, 25 | §2 Flow diagrams, mission_trace_id |
