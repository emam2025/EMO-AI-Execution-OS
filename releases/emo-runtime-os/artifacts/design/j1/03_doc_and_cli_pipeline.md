# Phase J1 — Documentation & CLI Pipeline with Routing Guards

## 1. Documentation Generation Pipeline

The Documentation Portal is powered by a 5-stage deterministic pipeline that
transforms CodeGraph snapshots, Canon Laws, and F1 API Specs into published
documentation artifacts. Every stage is gated by a Safety Guard.

### Stage Map

```
                    ┌─────────────────────────────────────────────────────────┐
                    │              Doc Generation Pipeline                     │
                    │              (5 stages, 4 guards)                       │
                    └─────────────────────────────────────────────────────────┘

  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │  STAGE 1     │     │  STAGE 2     │     │  STAGE 3     │     │  STAGE 4     │     │  STAGE 5     │
  │ CodeGraph    │────>│ API Spec     │────>│ Canon        │────>│ Generate     │────>│ Publish      │
  │ Scan         │     │ Extraction   │     │ Validation   │     │ [MD/OpenAPI  │     │ Artifact     │
  └──────────────┘     └──────────────┘     └──────────────┘     │ /AsyncAPI]   │     └──────────────┘
         │                     │                    │            └──────────────┘            │
         │                     │                    │                  │                     │
    ┌────▼────┐          ┌────▼────┐          ┌────▼────┐          ┌▼────┐             ┌────▼────┐
    │ G-D1    │          │ G-D2    │          │ G-D3    │          │G-D4 │             │ G-D5    │
    │snapshot │          │spec     │          │canon     │          │det. │             │publish  │
    │valid    │          │complete  │          │100%      │          │doc  │             │target   │
    └─────────┘          └─────────┘          └─────────┘          └─────┘             └─────────┘
```

### Stage Details

#### Stage 1 — CodeGraph Scan
| Field | Value |
|-------|-------|
| Input | `codegraph_snapshot: Dict[str, Any]` (from CodeGraph v1) |
| Output | `extracted_structure: Dict[str, Any]` (modules, interfaces, dependencies) |
| Guard | **G-D1 (snapshot_valid)**: snapshot MUST contain `modules >= 1` AND `interfaces >= 0` AND `version != ""`. If snapshot is empty or stale, pipeline halts. |
| Determinism | Same snapshot + same extraction rules -> same structure (SHA-256 of output verified). |
| LAW/RULE | LAW 1 (Interface Authority), RULE 1 (Determinism), RULE 2 (Read-only) |

#### Stage 2 — API Spec Extraction
| Field | Value |
|-------|-------|
| Input | `runtime_version: str`, `spec_registry: Dict[str, Any]` |
| Output | `api_spec_payload: APISpecPayload` (OpenAPI/AsyncAPI formatted) |
| Guard | **G-D2 (spec_complete)**: spec MUST contain `endpoints >= 1` AND `schemas >= 1` AND `openapi_version != ""`. Missing endpoint definitions block extraction. |
| Determinism | Same runtime_version + spec_registry -> same APISpecPayload (spec_hash verified). |
| LAW/RULE | LAW 1 (Interface Authority), LAW 2 (Interface Contracts), RULE 1 (Determinism) |

#### Stage 3 — Canon Validation
| Field | Value |
|-------|-------|
| Input | `canon_version: str`, `extracted_structure + api_spec` from Stages 1+2 |
| Output | `validation_result: Dict[str, Any]` (compliance_pct, violations) |
| Guard | **G-D3 (canon_100)**: `compliance_pct == 100.0` AND `violations == []`. If canon compliance < 100%, pipeline FLAGS the artifact — proceeds with warning but tagged `draft`. |
| Determinism | Same canon_version + same codegraph snapshot -> same validation result. |
| LAW/RULE | LAW 1 (Interface Authority), LAW 5 (Observability), RULE 1 (Determinism), RULE 3 (Safety Guards) |

#### Stage 4 — Document Generation
| Field | Value |
|-------|-------|
| Input | Validated structure + spec + canon |
| Output | `DocArtifact` (MD, HTML, OpenAPI JSON, AsyncAPI JSON) |
| Guard | **G-D4 (doc_deterministic)**: Generation MUST use sorted keys, deterministic templates, SHA-256 content_hash. If same inputs produce different content_hash, guard FAILS. |
| Format branching | `output_format` determines template: `markdown` → MD reference, `openapi_json` → OpenAPI 3.1 spec, `asyncapi_json` → AsyncAPI 2.6 spec, `html` → HTML portal page |
| Determinism | **Deterministic Doc Guard**: `content_hash = SHA-256(input_hash + template_version + sorted_definitions)`. Same snapshot + canon version + api spec -> same artifact content_hash. Prevents Non-Deterministic Doc Drift. |
| LAW/RULE | LAW 1, LAW 2, LAW 12, RULE 1, RULE 3 |

#### Stage 5 — Artifact Publication
| Field | Value |
|-------|-------|
| Input | `DocArtifact` (validated, generated) |
| Output | `publish_receipt: SpecPublicationReceipt` |
| Guard | **G-D5 (publish_target_valid)**: `target_repository` MUST be in allowed list AND `publish_status != FAILED`. Publication blocked if target is unauthorized. |
| Rollback | Published artifacts carry `previous_content_hash` for rollback via `IAPISpecPublisher.rollback_spec()`. |
| LAW/RULE | LAW 5 (Observability), LAW 8 (Recoverability), RULE 4 (Isolation), RULE 5 (Recovery) |

---

## 2. CLI Routing Guard Matrix

Every CLI command is evaluated against routing guards before execution. The
matrix ensures CLI NEVER accesses ExecutionEngine, D8 services, or I-layer
components directly (LAW 13).

### Guard Evaluation Flow

```
CLI Command Request
       │
       ▼
┌──────────────────┐
│ 1. Parse command │
│    + flags       │
└────────┬─────────┘
         │
         ▼
┌────────────────────────────────────┐
│ 2. Evaluate Routing Guards        │
│    ┌──────────────────────────┐   │
│    │ G-R1: target_f1_api?     │   │
│    │ G-R2: target_codegraph?  │   │
│    │ G-R3: target_read_only?  │   │
│    │ G-R4: auth_token_valid?  │   │
│    │ G-R5: trace_id_injected? │   │
│    └──────────────────────────┘   │
└────────┬───────────────────────────┘
         │
    ┌────┴────┐
    │ DECISION │
    └────┬────┘
         │
    ┌────┴────────┐  ┌───────────────┐  ┌──────────────┐
    │ ALLOW       │  │ FLAG          │  │ BLOCK        │
    │ Route to    │  │ Route with    │  │ Return       │
    │ target      │  │ warning       │  │ Forbidden    │
    └────┬────────┘  └───────┬───────┘  └──────┬───────┘
         │                  │                  │
         ▼                  ▼                  ▼
    Execute            Execute +         Log + Return
    Command            Audit Flag        403 Error
```

### Routing Guard Table

| Guard | Condition | Block If | Target Layer | LAW/RULE |
|-------|-----------|----------|--------------|----------|
| **G-R1** | `cli_command_allowed_only_if_targets_f1_api` | Command mutates state AND target is NOT F1 UnifiedRuntime | `f1_unified_api` | LAW 13 (No Direct Execution) |
| **G-R2** | `cli_command_allowed_only_if_targets_codegraph_read_only` | Command writes to CodeGraph (CodeGraph is read-only from CLI) | `codegraph_read` | LAW 1, RULE 2 |
| **G-R3** | `requires_runtime == True AND runtime_unreachable` | Runtime is unreachable — command cannot execute | `blocked` | LAW 5 (Observability) |
| **G-R4** | `auth_token_valid == False` | Auth token is missing, expired, or invalid | `blocked` | LAW 2 (Interface Authority) |
| **G-R5** | `trace_id_injected == True` | `devex_trace_id` is empty or malformed | `blocked` | LAW 12 (Traceability) |

### CLI Command Routing Table

| Command | Subcommand | Access Level | Target | Guards Applied |
|---------|-----------|--------------|--------|----------------|
| `emo` | `status` | READ_ONLY | F1 UnifiedRuntime (`/health`) | G-R3, G-R5 |
| `emo` | `logs <trace_id> --tail N` | READ_ONLY | F4 Observability (via F1) | G-R3, G-R4, G-R5 |
| `emo` | `replay <execution_id>` | F1_PROXIED | F1 UnifiedRuntime (`replay()`) | G-R1, G-R3, G-R4, G-R5 |
| `emo` | `validate <config_path>` | CODEGRAPH_ONLY | CodeGraph v1 (read-only) | G-R2, G-R5 |
| `emo` | `doc generate --type <type>` | CODEGRAPH_ONLY | DocGenerator pipeline | G-R2, G-R4, G-R5 |
| `emo` | `spec publish <spec>` | F1_PROXIED | IAPISpecPublisher | G-R1, G-R3, G-R4, G-R5 |
| `emo` | `spec rollback <spec_id>` | F1_PROXIED | IAPISpecPublisher | G-R1, G-R3, G-R4, G-R5 |
| `emo` | `help [command]` | READ_ONLY | Local help (no runtime) | (none — local only) |

---

## 3. Deterministic Doc Guard (DDG)

The Deterministic Doc Guard prevents **Non-Deterministic Doc Drift** — a
situation where the same source inputs produce different documentation output
across generations.

### DDG Algorithm

```
DDG(content_hash_actual, content_hash_expected) → bool

1. Hash Inputs (sorted keys):
   input_hash = SHA-256(
       sorted(codegraph_snapshot.modules) +
       sorted(api_spec.path_definitions) +
       canon_version +
       template_version
   )

2. Generate Content:
   content = render(template=input_hash, definitions=sorted_definitions)

3. Compute Actual Hash:
   content_hash_actual = SHA-256(content)

4. Compare:
   IF content_hash_actual == content_hash_expected:
       PASS — content is deterministic
   ELSE:
       FAIL — content drift detected → re-publish required
```

### DDG Enforcement Points

| Stage | Input Hash Components | Expected Hash Source | Action on Mismatch |
|-------|---------------------|---------------------|-------------------|
| CodeGraph extraction | modules + interfaces + version | Previous extraction hash | Re-extract |
| API spec generation | endpoints + schemas + openapi_version | spec_hash from APISpecPayload | Re-validate |
| Canon rendering | canon_version + output_format | content_hash from render_canon_laws() | Re-render |
| Final artifact | input_hash + template_version + sorted_definitions | content_hash on DocArtifact | Flag as `draft`, block `published` |

### DDG Properties

| Property | Guarantee |
|----------|-----------|
| **Determinism** | Same codegraph_snapshot + canon_version + api_spec -> same content_hash |
| **Idempotency** | Generating the same artifact twice produces identical content_hash |
| **Integrity** | content_hash changes IFF source inputs change |
| **Drift Detection** | Any hash mismatch is detected before publish — drift never reaches production docs |
| **Rollback** | Previous content_hash is preserved for `IAPISpecPublisher.rollback_spec()` |

---

## 4. Pipeline State Machine

The documentation pipeline can be modelled as a lightweight state machine:

```
┌─────────┐  G-D1   ┌──────────┐  G-D2   ┌──────────┐  G-D3   ┌──────────┐  G-D4   ┌──────────┐  G-D5   ┌──────────┐
│  IDLE   │──────>  │  SCAN    │──────>  │ EXTRACT  │──────>  │VALIDATE  │──────>  │ GENERATE │──────>  │ PUBLISH  │
└─────────┘         └──────────┘         └──────────┘         └──────────┘         └──────────┘         └──────────┘
     │                    │                     │                    │                     │                    │
     │                    ▼                     │                    │                     │                    │
     │              ┌──────────┐                │                    │                     │                    │
     └──────────────│  FAIL    │◄───────────────┴────────────────────┴─────────────────────┴────────────────────┘
                    │ (revert) │
                    └──────────┘
```

### Transition Table

| # | From | To | Guard | Condition |
|---|------|----|-------|-----------|
| P1 | IDLE | SCAN | G-D1 | snapshot_valid == true |
| P2 | SCAN | EXTRACT | G-D2 | spec_complete == true |
| P3 | EXTRACT | VALIDATE | G-D3 | canon_100 == true |
| P4 | VALIDATE | GENERATE | G-D4 | doc_deterministic == true |
| P5 | GENERATE | PUBLISH | G-D5 | publish_target_valid == true |
| P6 | ANY | FAIL | (any guard fails) | Guard condition not met |
| P7 | FAIL | IDLE | — | Manual reset after issue resolution |

---

## 5. Acceptance Criteria

| Criterion | Condition | Verification |
|-----------|-----------|--------------|
| All 5 stages defined | Stages 1-5 each have input, output, guard | Pipeline diagram + table |
| CLI routing matrix complete | All CLI commands mapped with guard rules | CLI routing table (8 commands) |
| Deterministic Doc Guard defined | DDG algorithm, enforcement points, properties | DDG section §3 |
| No direct runtime access | G-R1 blocks any command targeting non-F1 for writes | Routing guard G-R1 |
| devex_trace_id mandatory | G-R5 blocks any command without trace_id | Routing guard G-R5 |
| Pipeline state machine | States, transitions, guards for doc pipeline | §4 state machine |
