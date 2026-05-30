# Phase G4 — Tool Synthesis Agent: State Machine & Safety Guards
Date: 2026-05-22
Status: DESIGN ONLY
Ref: Canon LAW 2 (Interface Authority), LAW 8 (Governance), LAW 10 (Unreliable Workers)
Ref: Canon LAW 12 (Traceability), LAW 14 (Resource Governance)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation)
Ref: DEVELOPER.md §15.2, §15.10, §15.15b
Ref: ROADMAP Phase G4

---

## 1. State Map

```
                          ┌──────────────────────────────────────┐
                          │          INTENT_RECEIVED              │
                          │  (G1 intent + G3 opt proposal arrive) │
                          └────────────┬─────────────────────────┘
                                       │
                                       ▼
                          ┌──────────────────────────────────────┐
                          │         CODE_GENERATION               │
                          │  (IToolSynthesizer generates code     │
                          │   from intent + context)              │
                          └────────────┬──────────────────────────┘
                                       │
                                       ▼
                          ┌──────────────────────────────────────┐
                          │          AST_VALIDATION               │
                          │  (syntax check, banned imports,       │
                          │   capability extraction)              │
                          └────────────┬──────────────────────────┘
                                       │
                                       ▼
                          ┌──────────────────────────────────────┐
                          │          SECURITY_SCAN                │
                          │  (IToolValidator: os imports,         │
                          │   network access, risk scoring)       │
                          └───┬──────────────┬───────────────────┘
                              │              │
                     ┌────────┘      ┌───────┘
                     ▼               ▼
            ┌────────────────┐  ┌──────────────────────┐
            │ SANDBOX_DRY_RUN│  │     ESCALATE          │
            │ (Phase 4       │  │ (human-in-the-loop    │
            │  sandboxed     │  │  for unresolvable     │
            │  execution)    │  │  security violations)  │
            └───────┬────────┘  └──────────────────────┘
                    │
           ┌────────┼────────┐
           ▼        ▼        ▼
     ┌────────┐┌────────┐┌────────┐
     │REGISTER││ REJECT ││ESCALATE│
     │(auto-  ││(safety ││(if     │
     │ reg)   ││ guard  ││ dry-run│
     │        ││ fail)  ││ fails) │
     └────────┘└────────┘└────────┘
```

### Transition Table

| From | To | Guard | Description |
|------|----|-------|-------------|
| INTENT_RECEIVED | CODE_GENERATION | `guard_has_intent` | Intent must have goal + target_nodes |
| INTENT_RECEIVED | REJECT | `guard_incomplete_intent` | Intent missing mandatory fields |
| CODE_GENERATION | AST_VALIDATION | `guard_code_generated` | generated_code is non-empty |
| CODE_GENERATION | REJECT | `guard_generation_failed` | Code generation returned empty |
| AST_VALIDATION | SECURITY_SCAN | `guard_ast_valid` | ast_valid == true |
| AST_VALIDATION | REJECT | `guard_ast_invalid` | ast_valid == false |
| SECURITY_SCAN | SANDBOX_DRY_RUN | `guard_security_clear` | no_os_imports == true AND risk_score <= 0.3 |
| SECURITY_SCAN | ESCALATE | `guard_needs_escalation` | risk_score > 0.3 AND < 0.7 (ambiguous) |
| SECURITY_SCAN | REJECT | `guard_security_fail` | HIGH findings present OR risk_score >= 0.7 |
| SANDBOX_DRY_RUN | REGISTER | `guard_sandbox_passed` | dry_run success AND side_effects empty |
| SANDBOX_DRY_RUN | REJECT | `guard_sandbox_failed` | dry_run exception OR side_effects detected |
| SANDBOX_DRY_RUN | ESCALATE | `guard_sandbox_ambiguous` | success but resource_used near limits |
| REGISTER | (terminal) | — | Tool registered; emit `tool.available` |
| REJECT | (terminal) | — | Tool rejected; emit `tool.synthesis.failed` |
| ESCALATE | (terminal) | — | Escalated; emit `tool.synthesis.escalated` |

---

## 2. Safety Guards Matrix (RULE 3)

A tool SHALL be registered **only when** ALL of the following guards pass:

| # | Guard | Condition | Source | Violation Response |
|---|-------|-----------|--------|-------------------|
| G1 | `ast_valid` | AST parses without syntax error | AST_VALIDATION | Reject; emit `SynthesisAstInvalid` |
| G2 | `no_os_imports` | Zero banned OS-level imports | SECURITY_SCAN → verify_no_os_imports | Reject; emit `SynthesisSecurityViolation` with severity=HIGH |
| G3 | `capability_match >= 0.8` | Declared capabilities match code | SECURITY_SCAN → check_capability_match | Reject OR require revision; emit `SynthesisCapabilityMismatch` |
| G4 | `confidence >= 0.7` | Aggregate validation confidence | SECURITY_SCAN → rate_confidence | Reject; emit `SynthesisInsufficientConfidence` |
| G5 | `sandbox_dry_run_success == true` | Dry-run completes without exception | SANDBOX_DRY_RUN → execute_dry_run | Reject; emit `SynthesisSandboxFailure` |
| G6 | `side_effects_empty` | No blocked side effects observed | SANDBOX_DRY_RUN → capture_side_effects | Escalate; emit `SynthesisSideEffectDetected` |
| G7 | `risk_score <= 0.3` | Security risk within acceptable range | SECURITY_SCAN → analyze_security_risk | Escalate if <= 0.7; Reject if > 0.7 |

### Combined Registration Guard (Pseudocode)

```
def can_register(report: ValidationReport, sandbox: SandboxResult) -> bool:
    return (
        report.ast_valid                                                   # G1
        and report.no_os_imports                                           # G2
        and report.capability_match_score >= 0.8                            # G3
        and report.confidence_score >= 0.7                                  # G4
        and sandbox.success                                                 # G5
        and len(sandbox.side_effects) == 0                                  # G6
        and report.overall_risk_score <= 0.3                                # G7
    )
```

### Guard Scoring Weights (for confidence computation)

| Component | Weight | Condition |
|-----------|--------|-----------|
| AST valid | +0.30 | ast_valid == true |
| No OS imports | +0.30 | no_os_imports == true |
| Capability match | +0.20 | capability_match_score >= 0.8 |
| Security clean | +0.20 | overall_risk_score <= 0.2 |
| Each HIGH finding | -0.20 | Per finding |
| Each MEDIUM finding | -0.10 | Per finding |

Formula: `confidence = min(1.0, max(0.0, base_score + penalties + bonuses))`

---

## 3. Deterministic Synthesis Guard (RULE 1)

The Synthesizer MUST produce the **same generated code** for the same
`(intent, context, capability_set)` input triple, regardless of execution
time, system load, or random state.

### Mechanism

```
synthesis_cache_key = sha256(
    normalize(intent) +
    normalize(context) +
    normalize(capability_set)
).hexdigest()

# If cache_key exists → return cached generated_code + ast_hash
# If cache_key does not exist → generate, hash, store, return
```

### Determinism Guarantees

| Layer | Determinism Strategy |
|-------|---------------------|
| Code generation | Template-based generation; no LLM / no random sampling |
| AST hashing | SHA-256 of canonical AST (sorted nodes, normalised literals) |
| Capability extraction | Deterministic AST visitor; sorted output |
| Signature derivation | Pure function of AST; deterministic ordering |
| Risk scoring | Threshold comparison + sorted finding iteration |

### Non-Deterministic Drift Prevention

If the Deterministic Synthesis Guard detects that:
- The same `synthesis_cache_key` produces different `generated_code`
- OR the same `code` produces different `ast_hash`
- OR the same `ast_hash` produces different `capability_set`

Then:
1. Emit `SynthesisDriftDetected(intent_id, synthesis_trace_id, expected_hash, actual_hash)` to EventBus
2. Set state to REJECT
3. Log determinism violation for F4 Observability
4. Require supervisor review before next synthesis for this intent

---

## 4. State Machine Parameter Summary

| Parameter | Default | Min | Max | Description |
|-----------|---------|-----|-----|-------------|
| min_capability_match | 0.8 | 0.5 | 1.0 | Minimum capability match score |
| min_confidence_threshold | 0.7 | 0.5 | 1.0 | Minimum aggregate confidence |
| max_risk_score | 0.3 | 0.0 | 1.0 | Maximum acceptable risk |
| escalation_risk_threshold | 0.7 | 0.3 | 1.0 | Risk above this → reject (not escalate) |
| sandbox_timeout_sec | 30.0 | 5.0 | 120.0 | Max dry-run duration |
| symmetry_cache_ttl_s | 3600 | 60 | 86400 | Determinism cache TTL |
| max_side_effect_size_bytes | 1024 | 256 | 1048576 | Max captured side-effect detail |

---

## 5. EventBus Topics

| Topic | Emitted When |
|-------|-------------|
| `tool.synthesis.started` | INTENT_RECEIVED state entered |
| `tool.synthesis.completed` | REGISTER state entered |
| `tool.synthesis.failed` | REJECT state entered |
| `tool.synthesis.security_violation` | G2 or G4 guard fails |
| `tool.synthesis.escalated` | ESCALATE state entered |
| `tool.synthesis.registered` | Tool registered in ToolRegistry |
| `tool.synthesis.rolled_back` | Rollback executed |
| `tool.available` | Registration propagated |
| `tool.synthesis.drift_detected` | Determinism hash mismatch |
| `sandbox.cleaned` | Sandbox cleanup completed |
| `synthesis.capability_mismatch` | Capability match guard fails |
| `synthesis.side_effect_detected` | Side effects found after dry-run |
