# Phase G4 — Tool Synthesis Agent: Integration Blueprint
Date: 2026-05-22
Status: DESIGN ONLY
Ref: Canon LAW 2 (Interface Authority), LAW 10 (Unreliable Workers), LAW 12 (Traceability)
Ref: Canon LAW 14 (Resource Governance), RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation)
Ref: DEVELOPER.md §15.2, §15.10, §15.15b
Ref: ROADMAP Phase G4

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         G4 Tool Synthesis Agent                      │
│                                                                      │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ ITool      │  │ ITool        │  │ ITool       │  │ ITool      │ │
│  │ Synthesizer│──│ Validator    │──│ Sandboxer   │──│ Registry   │ │
│  │            │  │              │  │             │  │ Manager    │ │
│  └─────┬──────┘  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘ │
│        │                │                 │               │         │
│  ┌─────┴────────────────┴─────────────────┴───────────────┴──────┐ │
│  │               Synthesis State Machine                          │ │
│  │  INTENT → CODE → AST → SECURITY → SANDBOX → [REGISTER/REJECT] │ │
│  │                       → ESCALATE                               │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
         ▲                ▲              ▲               ▲
         │                │              │               │
    ┌────┴────┐     ┌─────┴──────┐  ┌───┴────┐    ┌─────┴──────┐
    │  G1     │     │  G3        │  │ Phase 4 │    │ Tool      │
    │ Planner │     │ Optimizer  │  │ Sandbox │    │ Registry  │
    │ Agent   │     │ Agent      │  │(Isolat.)│    │(D8 / DI)  │
    └─────────┘     └────────────┘  └─────────┘    └────────────┘
```

## 2. Data Flow

### 2.1 G1 Planner → G4 Synthesizer

Triggered when G1 Planner encounters an intent whose target DAG node requires
a tool that does not exist in ToolRegistry.

```
G1 Planner Agent                    G4 Tool Synthesis Agent
─────────────────                   ────────────────────────
  │                                        │
  │  synthesizer.synthesize_from_intent(   │
  │    intent={                            │
  │      intent_id,                        │
  │      goal,                             │
  │      target_nodes,                     │
  │      constraints,                      │
  │      confidence                        │
  │    },                                  │
  │    context={                           │
  │      plan_id,                          │
  │      dag_topology,                     │
  │      node_capabilities,                │
  │      sandbox_profile,                  │
  │      optimizer_trace_id                │
  │    }                                   │
  │  ) ──────────────────────────────────► │
  │                                        │
  │  ◄───────────────────────────────────  │
  │  return {                              │
  │    generated_code,                     │
  │    ast_hash,                           │
  │    capability_set,                     │
  │    estimated_risk_score,               │
  │    synthesis_trace_id                  │
  │  }                                     │
```

### 2.2 G3 Optimizer → G4 Synthesizer

When G3 proposes a topology patch that requires a new synthesised tool
(e.g., a merged/reordered node needs a unified capability), G3 includes
`requires_synthesis: true` and `proposed_capabilities` in its patch.

```
G3 Optimizer Agent                  G4 Tool Synthesis Agent
─────────────────                   ────────────────────────
  │                                        │
  │  Patch with requires_synthesis=true    │
  │  ───────────────────────────────────►  │
  │                                        │
  │  synthesis_trace_id correlated         │
  │  back to optimizer_trace_id            │
```

### 2.3 G4 Validator → AST & Security Pipeline

```
IToolValidator Pipeline
───────────────────────
  generated_code
       │
       ▼
  ┌─────────────────┐
  │ AST parse        │──── ast_valid? ────► false → REJECT
  └────────┬─────────┘
           │
           ▼
  ┌─────────────────┐
  │ verify_no_os     │──── has OS imports? ─► false → REJECT + SECURITY_VIOLATION
  │ imports()        │
  └────────┬─────────┘
           │
           ▼
  ┌─────────────────┐
  │ check_capability │──── match < 0.8? ────► REJECT or REQUIRE_REVISION
  │ match()          │
  └────────┬─────────┘
           │
           ▼
  ┌─────────────────┐
  │ analyze_security │──── risk > 0.3? ────► ESCALATE (if <= 0.7) / REJECT (if > 0.7)
  │ risk()           │
  └────────┬─────────┘
           │
           ▼
  ┌─────────────────┐
  │ rate_confidence()│──── confidence < 0.7? ──► REJECT
  └────────┬─────────┘
           │
           ▼
     ValidationReport
  (passed to SANDBOX_DRY_RUN or REJECT)
```

### 2.4 G4 Sandboxer → Phase 4 Isolation

```
Phase 4 Sandbox API                    IToolSandboxer
────────────────────                   ──────────────
                   │                              │
                   │  prepare_sandbox_context()    │
                   │  ───────────────────────────► │
                   │  ◄─────────────────────────── │
                   │  sandbox_ctx                  │
                   │                              │
                   │  execute_dry_run(sandbox_ctx) │
                   │  ───────────────────────────► │
                   │  ◄─────────────────────────── │
                   │  {success, output,            │
                   │   resource_used, duration_ms}  │
                   │                              │
                   │  capture_side_effects(ctx)    │
                   │  ───────────────────────────► │
                   │  ◄─────────────────────────── │
                   │  [{effect_type, target,       │
                   │    value, blocked}]            │
                   │                              │
                   │  cleanup_sandbox(ctx)          │
                   │  ───────────────────────────► │
                   │  ◄─────────────────────────── │
```

### 2.5 G4 Registry Manager → ToolRegistry (D8 / DI)

```
IToolRegistryManager                    ToolRegistry
────────────────────                    ────────────
                  │                              │
                  │  validate_registration       │
                  │  _compliance(metadata)        │
                  │  ───────────────────────────► │
                  │  ◄─────────────────────────── │
                  │  true / false                 │
                  │                              │
                  │  register_synthesized_tool(   │
                  │    tool_metadata)              │
                  │  ───────────────────────────► │
                  │  ◄─────────────────────────── │
                  │  {registration_id, status,     │
                  │   rollback_token}              │
                  │                              │
                  │  publish_tool_available_event( │
                  │    tool_id, signature)          │
                  │  ───────────────────────────► │
                  │         EventBus               │
                  │         topic: tool.available  │
```

---

## 3. Correlation ID Propagation (LAW 12)

### Trace Chain

```
G1 Planner           G4 Synthesizer           G4 Validator
plan_id ──────────► synthesis_trace_id ───► synthesis_trace_id
    │                                            │
    │               G4 Sandboxer                  │
    │               synthesis_trace_id ◄──────────┘
    │                    │
    │               G4 Registry Manager
    │               synthesis_trace_id
    │                    │
    └────────────────────┼────────────────────────┘
                         │
                    EventBus Topics:
                    tool.synthesis.*
                    tool.available
```

### ID Format

```
synthesis_trace_id = "syn_{sha256(intent_id + plan_id + time_ns)[:24]}"
```

### Cross-Layer Correlation Table

| Layer | Trace ID Field | Propagated To |
|-------|---------------|---------------|
| G1 Planner | plan_id | G4 via intent.context.plan_id |
| G3 Optimizer | optimizer_trace_id | G4 via intent.context.optimizer_trace_id |
| G4 Synthesizer | synthesis_trace_id | All G4 sub-protocols + EventBus |
| Phase 4 Sandbox | synthesis_trace_id | Sandbox session log |
| ToolRegistry | synthesis_trace_id | Registration metadata |
| F4 Observability | synthesis_trace_id | All G4 trace spans |

---

## 4. Hook Points for EventBus Topics

| Hook | Stage | Topic | Payload |
|------|-------|-------|---------|
| Synthesis started | INTENT_RECEIVED | `tool.synthesis.started` | {intent_id, plan_id, synthesis_trace_id} |
| Code generated | CODE_GENERATION | `tool.synthesis.code_generated` | {synthesis_trace_id, ast_hash, capability_set} |
| AST invalid | AST_VALIDATION → REJECT | `tool.synthesis.failed` | {synthesis_trace_id, reason: "ast_invalid"} |
| Security violation | SECURITY_SCAN → REJECT | `tool.synthesis.security_violation` | {synthesis_trace_id, severity, findings[]} |
| Capability mismatch | SECURITY_SCAN → REVISION | `synthesis.capability_mismatch` | {synthesis_trace_id, mismatches[]} |
| Side effect detected | SANDBOX_DRY_RUN → ESCALATE | `synthesis.side_effect_detected` | {synthesis_trace_id, effects[]} |
| Sandbox failure | SANDBOX_DRY_RUN → REJECT | `tool.synthesis.failed` | {synthesis_trace_id, reason: "sandbox_failure"} |
| Drift detected | Any state | `tool.synthesis.drift_detected` | {intent_id, synthesis_trace_id, expected_hash, actual_hash} |
| Registration complete | REGISTER | `tool.synthesis.registered` | {tool_id, synthesis_trace_id, registration_id} |
| Registration rejected | REJECT | `tool.synthesis.failed` | {tool_id, synthesis_trace_id, failed_guards[]} |
| Registration rolled back | ROLLED_BACK | `tool.synthesis.rolled_back` | {tool_id, rollback_token} |

---

## 5. Acceptance Criteria for Integration

### 5.1 Latency Budgets

| Operation | Target | Hard Limit |
|-----------|--------|------------|
| Code generation | 500ms | 2000ms |
| AST validation + security scan | 200ms | 1000ms |
| Sandbox dry-run | 5000ms | 30000ms |
| Registration | 100ms | 500ms |
| Total (synthesize → register) | 6000ms | 35000ms |

### 5.2 Idempotency Guarantees

| Operation | Idempotency Key | Behaviour |
|-----------|----------------|-----------|
| `synthesize_from_intent` | Deterministic cache key | Same input → same code (RULE 1) |
| `register_synthesized_tool` | (tool_id, rollback_token) | Duplicate registration returns existing registration_id |
| `rollback_registration` | rollback_token | Already-rolled-back returns True |

### 5.3 Determinism Thresholds

| Metric | Threshold |
|--------|-----------|
| Same intent → same code | 100% required |
| Same code → same ast_hash | 100% required |
| Same ast_hash → same capability_set | 100% required |
| Same code → same risk_score | ±0.05 tolerance (due to path-based scoring order) |

### 5.4 Rollback on Failure

Any failure after REGISTER state requires:

1. Call `IToolRegistryManager.rollback_registration(tool_id, rollback_token)`
2. Emit `tool.synthesis.rolled_back` on EventBus
3. Clean up any sandbox artifacts via `cleanup_sandbox()`
4. Log full failure chain with synthesis_trace_id to F4

---

## 6. CompositionRoot Integration (for future implementation)

When G4 is implemented in `core/`, the CompositionRoot will gain:

```python
# In CompositionRoot.__init__:
synthesizer_agent: Any = None
strict_synthesis_mode: bool = False

# Property:
@property
def tool_synthesizer(self) -> Any:
    """Return IToolSynthesizer instance (Phase G4)."""

# Builder:
def _build_tool_synthesizer(self) -> Any:
    from core.runtime.synthesis.tool_synthesizer import ToolSynthesizer
    from core.runtime.synthesis.tool_validator import ToolValidator
    from core.runtime.synthesis.tool_sandboxer import ToolSandboxer
    from core.runtime.synthesis.tool_registry_manager import ToolRegistryManager
    from core.runtime.synthesis.synthesis_state_machine import SynthesisStateMachine
    from core.runtime.synthesis.trace_correlator import SynthesisTraceCorrelator
    # ... build and wire ...
```

This maps to the existing pattern used by G1, G2, and G3 in `core/composition/root.py`.
