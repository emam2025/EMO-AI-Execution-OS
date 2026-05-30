# R3 Skill OS — Architecture Manifest

**Directive**: EXEC-DIRECTIVE-R3-PREP-001
**Stage**: R3 — Skill OS Foundation & Extraction Protocol Design
**Isolation**: ZERO R1/R2 MUTATIONS | PROTOCOL-ONLY | ISOLATION-BOUND
**Date**: 2026-05-30

---

## 1. Architecture Overview

R3 Skill OS is a protocol-only layer that defines **how skills are extracted** from R2 Memory traces and **how they evolve** through lifecycle tiers. It has zero runtime, zero storage, and zero execution logic.

```
R2 Memory OS ──(read-only)──► ISkillExtractor ──► SkillDraft ──► SkillStore (future)
                                    │
                                    ▼
                          ISkillEvolutionManager
                                    │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
                Draft          Verified         Optimized
                    │                │                │
                    └────────────────┼────────────────┘
                                     ▼
                              Deprecated
```

## 2. Isolation Matrix

| Layer | Accessible from R3? | Direction | Constraint |
|-------|---------------------|-----------|------------|
| R2 Memory OS | ✅ Read-only via protocol | R3 → R2 | Via ISkillExtractor only |
| R1 Runtime OS | ❌ | — | No access; completely sealed |
| Core ExecutionEngine | ❌ | — | Never imported or referenced |
| R2 Governance | ❌ | — | Retention is R2's concern only |
| R2 UI (emo-memory-explorer) | ❌ | — | R3 has its own emo-skill-library UI |
| R3 Skill Store | ⏳ Future | — | Reserved for implementation phase |

## 3. Skill Evolution Lifecycle

```
    ┌──────────┐     promote()     ┌──────────┐     promote()     ┌──────────┐
    │  DRAFT   │ ────────────────► │ VERIFIED │ ────────────────► │ OPTIMIZED│
    └──────────┘                   └──────────┘                   └──────────┘
         │                              │                              │
         └────────── deprecate() ───────┼──────────────────────────────┘
                                        ▼
                                 ┌──────────────┐
                                 │  DEPRECATED  │
                                 └──────────────┘
```

- **Draft**: Initial extraction from trace, not yet validated.
- **Verified**: Pattern validated by `validate_pattern()` and manual review.
- **Optimized**: Refined through repeated execution and feedback.
- **Deprecated**: Superseded or retired; can be re-promoted with new evidence.

## 4. Guard OS Boundaries

| Boundary | Rule | Enforcement |
|----------|------|-------------|
| **Skills are extracted, not executed** | R3 never calls ExecutionEngine or any runtime | Protocol-only design; zero import of runtime modules |
| **Evolution requires validator signature** | `promote()` accepts optional `validator_signature` | Model-level field; future implementation must verify |
| **Rollback via deprecate()** | Any tier can transition to Deprecated | `ISkillEvolutionManager.deprecate()` with reason |
| **No direct R2 access** | R3 reads R2 only through ISkillExtractor | Interface contract; no direct `from releases.memory_os` imports |
| **Tenant isolation** | Every model enforces tenant_id | `SkillNode.__post_init__()` raises on empty tenant_id |
| **Tier isolation** | Every skill has exactly one tier | `SkillNode.tier` is mandatory SkillTier enum |

## 5. Protocol Contracts

### ISkillExtractor

```python
extract_from_trace(trace_id, tenant_id, project_id)          → ISkillDraft
validate_pattern(pattern, tenant_id)                          → bool
list_extractable_traces(tenant_id, project_id, min_confidence, limit) → List[str]
```

### ISkillEvolutionManager

```python
promote(skill_id, new_tier, tenant_id, validator_signature)   → SkillEvolutionRecord
deprecate(skill_id, reason, tenant_id)                        → SkillEvolutionRecord
get_evolution_history(skill_id, tenant_id)                    → List[SkillEvolutionRecord]
current_tier(skill_id, tenant_id)                             → SkillTier
```

## 6. Data Models

| Model | Key Fields | Invariants |
|-------|-----------|------------|
| `SkillNode` | skill_id, tenant_id, skill_name, pattern_hash, confidence_score, tier | tenant_id mandatory, confidence ∈ [0,1], tier enum |
| `ExecutionBlueprint` | blueprint_id, skill_id, tenant_id, steps[], tool_sequence[], failure_guardrails[] | tenant_id mandatory |
| `SkillEvolutionRecord` | record_id, skill_id, tenant_id, from_tier, to_tier, validator_signature | tenant_id mandatory |
| `SkillStoreEntry` | entry_id, skill, blueprints[], evolution_history[] | entry_id mandatory |

## 7. Canon Compliance

| Law | Requirement | R3 Implementation |
|-----|-------------|-------------------|
| LAW-6 | tenant_id mandatory at every public method | `ISkillExtractor`, `ISkillEvolutionManager`, all models enforce tenant_id |
| LAW-8 | No cross-tenant data leakage | Every model scopes by tenant_id; future SkillStore must filter by tenant_id |
| LAW-11 | Tenant isolation at storage and query layers | `list_extractable_traces()` filters by tenant_id + project_id |
| LAW-14 | Protocol boundaries | R3 is protocol-only; no execution or storage logic |

## 8. Skill Hash Propagation Chain

```
R2 Memory Trace ──(trace_id)──► ISkillExtractor.extract_from_trace()
                                      │
                                      ▼
                              pattern_hash = SHA-256(pattern)
                                      │
                                      ▼
                              SkillNode.pattern_hash
                                      │
                                      ▼
                              ISkillEvolutionManager.promote()
                                      │
                                      ▼
                              SkillEvolutionRecord (audit trail)
```

Each step in the chain preserves the `pattern_hash` for verifiability.

## 9. File Map

```
/releases/skill-os/
├── core/
│   ├── interfaces/skills/
│   │   ├── ISkillExtractor.py
│   │   └── ISkillEvolutionManager.py
│   ├── models/
│   │   └── skills.py
│   └── skills/                          # Empty (reserved)
├── desktop/
│   └── emo-skill-library/src/App.tsx    # 4 route stubs
├── docs/
│   └── R3_SKILL_ARCHITECTURE_MANIFEST.md
├── tests/
│   └── test_r3_isolation_and_contracts.py
├── artifacts/
│   ├── RELEASE_MANIFEST_R3_DRAFT.json
│   └── execution_log.txt
└── certificates/
    └── R3_PREP_CERTIFICATE.json
```

## 10. Stop Conditions

| Condition | Action |
|-----------|--------|
| Import from `releases.runtime_os` or `releases.memory_os` | 🛑 STOP + REVERT |
| Any execution/storage logic in protocol files | 🛑 STOP + REVERT |
| tenant_id or tier not mandatory on models | 🛑 STOP + ADD GUARD |
| Any mutation to `releases/runtime-os/` or `releases/memory-os/` | 🛑 STOP + AUDIT |
