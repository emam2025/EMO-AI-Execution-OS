# Phase H1 — Computer Use Session State Machine & Interaction Guards

## State Overview

The Computer Use Runtime defines a **6-state lifecycle machine** for every
browser/desktop/vision session. Each transition is gated by **Interaction Guards**
that enforce Canon LAW 10 (Unreliable Workers), RULE 2 (No Uncontrolled IO),
and RULE 3 (Safety Guards).

### States

| State | Description | LAW/RULE |
|-------|-------------|----------|
| `INIT` | Session allocated, no worker attached | LAW 10 |
| `READY` | Worker sandboxed, capabilities verified, awaiting action | RULE 2, RULE 4 |
| `INTERACTING` | Action in progress (navigation, click, type, vision) | LAW 24 |
| `PAUSED` | Session suspended, checkpoint available | LAW 10 |
| `CHECKPOINTED` | Journal state saved, deterministic hash captured | RULE 1 |
| `TERMINATED` | Session ended, resources released | LAW 10, RULE 4 |

---

## Transition Map

```
                      ┌──────────────────────────────────────────────┐
                      │                                              │
                      v                                              │
   ┌──────┐  G1    ┌──────┐  G2,G3 ┌─────────────┐  G7,G8  ┌──────┐ │
   │ INIT │───────>│ READY│───────>│ INTERACTING │────────>│PAUSED│ │
   └──────┘        └──────┘        └─────────────┘         └──────┘ │
      │               │                │  │                 │       │
      │               │                │  │                 │       │
      │        G10    │       G4,G5    │  │                 │       │
      │     ┌─────────┘    ┌──────────┘  │                 │       │
      │     │              │             │                 │       │
      v     v              v             v                 v       │
   ┌──────────────────────────────────────────────────────────┐     │
   │                       TERMINATED                          │─────┘
   └──────────────────────────────────────────────────────────┘

   G9 ─── CHECKPOINTED ─── G11 (from INTERACTING or PAUSED)
     │                        ^
     └──── replay/rollback ───┘
```

### Transition Table

| # | From | To | Guard | Conditions | LAW/RULE |
|---|------|----|-------|------------|----------|
| G1 | INIT | READY | `guard_capability_check` | isolation_context AND capabilities AND sandbox_token all valid | LAW 10, RULE 2 |
| G2 | READY | INTERACTING | `guard_action_dispatch` | action_type valid AND sandbox_token matches session | LAW 24 |
| G3 | READY | INTERACTING | `guard_vision_grounding` | (for vision actions) visual_context_hash OR selector provided | RULE 1, RULE 3 |
| G4 | INTERACTING | READY | `guard_action_complete` | action returned result AND no critical error | LAW 24 |
| G5 | INTERACTING | READY | `guard_grounding_miss` | (vision fallback) grounding confidence < 0.7 AND fallback requested | RULE 3 |
| G6 | INTERACTING | TERMINATED | `guard_unrecoverable_error` | critical error OR capability violation OR sandbox breach | LAW 10 |
| G7 | INTERACTING | PAUSED | `guard_can_pause` | has_checkpoint AND no inflight critical operation | LAW 10, RULE 3 |
| G8 | READY | PAUSED | `guard_idle_pause` | idle_timeout_sec exceeded OR user-initiated pause | LAW 10 |
| G9 | INTERACTING/PAUSED | CHECKPOINTED | `guard_checkpoint` | session state valid AND journal call succeeds AND state_hash computed | RULE 1 |
| G10 | READY | TERMINATED | `guard_terminate` | session expired OR resources exhausted OR governance signal | LAW 10, RULE 4 |
| G11 | CHECKPOINTED | READY | `guard_replay_verified` | replay succeeded OR rollback completed AND state_hash matches expected | RULE 1 |
| G12 | PAUSED | TERMINATED | `guard_pause_timeout` | pause_duration exceeds max_pause_sec | LAW 10 |

---

## Interaction Guards (I1–I8)

### I1 — Selector Validity Guard (`guard_selector_valid`)
**Prevents:** Actions targeting non-existent or ambiguous elements.

| Condition | Pass | Fail |
|-----------|------|------|
| target_selector is non-empty | ✅ | ❌ Block with `BLOCKED_SELECTOR` |
| selector resolves to ≤1 element in DOM/A11y tree | ✅ | ❌ Block with `BLOCKED_SELECTOR: ambiguous` |
| selector element is visible (not `display:none`, `aria-hidden`) | ✅ | ❌ Block with `BLOCKED_SELECTOR: hidden` |
| **LAW:** RULE 2 — No Uncontrolled IO | | |

### I2 — Spatial Bounding Box Guard (`guard_spatial_bbox_verified`)
**Prevents:** Click/type targets outside safe interaction region.

| Condition | Pass | Fail |
|-----------|------|------|
| click coordinates within viewport | ✅ | ❌ Block with `BLOCKED_SPATIAL: out_of_viewport` |
| (click) target bbox not covered by obstructive overlay | ✅ | ❌ Block with `BLOCKED_SPATIAL: covered` |
| (type) target element is focusable (input, textarea, [contenteditable]) | ✅ | ❌ Block with `BLOCKED_SPATIAL: not_focusable` |
| **LAW:** LAW 10 — Unreliable Workers, RULE 2 | | |

### I3 — Capability Match Guard (`guard_capability_match`)
**Prevents:** Actions requiring undeclared capabilities.

| Condition | Pass | Fail |
|-----------|------|------|
| session.capabilities contains action capability | ✅ | ❌ Block with `BLOCKED_CAPABILITY` |
| sandbox_token matches session.sandbox_token | ✅ | ❌ Block with `BLOCKED_SANDBOX` |
| action_type permitted by isolation_context.capability_guard | ✅ | ❌ Block with `BLOCKED_CAPABILITY: guard_denied` |
| **LAW:** LAW 10, RULE 2 | | |

### I4 — Session Isolation Guard (`guard_session_isolation`)
**Prevents:** Cross-session contamination or outside-session execution.

| Condition | Pass | Fail |
|-----------|------|------|
| session.state is READY or INTERACTING | ✅ | ❌ Block with `BLOCKED_SANDBOX: wrong_state` |
| session.session_id matches action context | ✅ | ❌ Block: session mismatch |
| worker_pid is alive (health check) | ✅ | ❌ Block: worker_dead → TERMINATED |
| **LAW:** LAW 10, RULE 4 | | |

### I5 — Visual Grounding Consistency Guard (`guard_vision_consistency`)
**Prevents:** Actions grounded on stale or invalid visual context.

| Condition | Pass | Fail |
|-----------|------|------|
| visual_context_hash matches current screenshot hash | ✅ | ❌ Mark as stale_grounding → re-ground |
| detect_ui_element confidence ≥ 0.7 | ✅ | ❌ Flag low_confidence → human review |
| template_match confidence ≥ threshold param | ✅ | ❌ Exclude from matches |
| **LAW:** RULE 1 (Determinism), RULE 3 (Safety) | | |

### I6 — Journal Integrity Guard (`guard_journal_integrity`)
**Prevents:** Journal tampering or replay deviation.

| Condition | Pass | Fail |
|-----------|------|------|
| previous_entry_hash matches last journal entry hash | ✅ | ❌ Chain broken → STOP |
| state_hash chain is monotonic (sequence_number increases by 1) | ✅ | ❌ Gap detected → STOP |
| replay deviation < determinism_threshold (0.95 default) | ✅ | ❌ Abort replay → ROLLBACK |
| **LAW:** RULE 1 (Determinism), LAW 24 | | |

### I7 — Resource Quota Guard (`guard_resource_quota`)
**Prevents:** Session exceeding declared resource limits.

| Condition | Pass | Fail |
|-----------|------|------|
| cpu_sec < max_cpu_sec | ✅ | ❌ Pause session → notify F4 observability |
| memory_mb < max_memory_mb | ✅ | ❌ Pause session → trigger G5 escalation |
| action_count < max_actions | ✅ | ❌ Terminate session |
| session_duration < max_session_sec | ✅ | ❌ Terminate session |
| **LAW:** LAW 10 — Unreliable Workers | | |

### I8 — Deterministic Replay Guard (`guard_replay_determinism`)
**Prevents:** Non-deterministic replay sequences.

| Condition | Pass | Fail |
|-----------|------|------|
| action_stream matches saved journal sequence | ✅ | ❌ Abort — journal mismatch |
| same session_profile + action_stream → same state_hash | ✅ | ❌ Deviation detected → ROLLBACK |
| replay_state_chain matches expected_state_chain | ✅ | ❌ Abort replay → escalation |
| **LAW:** RULE 1 (Determinism) | | |

---

## Deterministic Replay Guard — Design

The Journal guarantees that **the same session_profile + action_stream produces the
same state_hash sequence every replay**. This is achieved through:

### Formula

```
state_hash_0 = H(session_profile)
state_hash_n = H(state_hash_{n-1} || action_payload_n || pre_action_visual_hash_n)
```

Where `H()` is SHA-256, `||` is concatenation, and `action_payload_n` includes:
- `action_type`, `target_selector`, `input_data`, `coordinates`, `modifiers`
- `visual_context_hash` (pre-action screenshot hash)
- `guard_status`, `duration_ms`, `error` (empty string if no error)

### Deviation Tolerance

| Metric | Threshold | Action |
|--------|-----------|--------|
| State hash deviation | 0% (strict) | Abort replay, rollback to last checkpoint |
| Visual diff (pixel) | ≤5% of viewport | Log warning, continue |
| Visual diff (structural) | ≤2 elements | Log warning, continue |
| Grounding confidence drop | ≥0.2 below original | Re-ground element, continue |
| Action duration variance | ±50% of original | Log warning, continue |
| **Determinism confidence** | **≥0.95** | **If below → abort, rollback** |

### Integration with SessionJournal.record_action

```python
def _compute_state_hash(
    prev_hash: str,
    action: ActionPayload,
    pre_action_visual_hash: str,
) -> str:
    raw = f"{prev_hash}:{action.sequence_number}:{action.action_type}:"
    raw += f"{action.target_selector}:{action.input_data}:"
    raw += f"{action.coordinates}:{pre_action_visual_hash}:"
    raw += f"{action.guard_status.value}:{action.error}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

---

## Session Lifecycle Compliance

| Concern | Guard | Enforcement |
|---------|-------|-------------|
| No action without capability match | I3 | Block before dispatch |
| No click without valid selector + spatial check | I1 + I2 | Block before execution |
| No uncontrolled IO outside sandbox | I4 | Block if session not READY |
| Stale visual grounding rejected | I5 | Re-ground before action |
| Journal integrity verified | I6 | Verify before replay |
| Resource limits enforced | I7 | Pause/terminate on breach |
| Deterministic replay guaranteed | I8 | Abort on deviation |
