# Architecture Ownership Map — Emo-AI

> **Purpose:** Document ownership of each folder, classify its affiliation to the ten layers (current and future), identify dependencies, and separate what exists now from what will be migrated later.
>
> **Branch Status:** `release/v1-production-candidate` — **Frozen**. No changes until Pilot ends.
>
> **Document Type:** Mapping Only — Not a Refactor execution plan.

---

## 1. Ten Layers — Present and Future Ownership

### 1.1 Agent OS

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/agents/` | **Full Ownership — Agent OS** | Stays in place |
| `core/agent_teams/` | **Full Ownership — Agent OS** | Stays in place |
| `core/planner/` | **Full Ownership — Agent OS** | Stays in place |
| `core/autonomous_control/` | **Full Ownership — Agent OS** | Stays in place |
| `core/autonomy/` | **Full Ownership — Agent OS** | Stays in place |

**Core Files:** `core/agents/planner_agent.py`, `critic_agent.py`, `adaptive_planner.py`, sector folders under `core/agents/{energy,manufacturing,water,healthcare}/`.

**Dependencies:** `core/models/` (event, planner, critic, agent), `core/interfaces/`, `core/governance/`, `core/security/`

---

### 1.2 Workflow OS

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/workflow_os/` | **Reserved / Target Ownership** — Future container for Workflow content | **Exists but currently empty** (only contains `__pycache__`). To be filled later |
| `core/workflow_runtime_v2/` | **Full Ownership — Workflow OS** | Stays in place |
| `core/canvas/` | **Sub Ownership — Workflow OS** (UI canvas) | Stays in place |
| `core/dag_*.py` | **Full Ownership — Workflow OS** | Stays in place |
| `routers/workflow.py` | **Full Ownership — Workflow API** | Stays in place |

**Proposed future content for `core/workflow_os/` (in refactor branch):**
- `workflow_engine.py` — DAG executor
- `workflow_validator.py` — DAG validation (currently in `routers/workflow.py`)
- `workflow_scheduler.py` — Workflow scheduling
- `workflow_models.py` — Workflow-specific models

**Dependencies:** `core/models/dag.py`, `core/models/event.py`, `core/runtime/`

---

### 1.3 Project OS

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/projectos/` | **Full Ownership — Project OS** | Stays in place |
| `routers/project.py` | **Full Ownership — Project API** | Stays in place |

**Dependencies:** `core/models/`, `core/security/`, `core/governance/`

---

### 1.4 Industrial OS

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/industrial/` | **Full Ownership — Industrial OS** | Stays in place |
| `core/industry_profiles/` | **Full Ownership — Industrial OS** | Stays in place |
| `core/digital_twin_v2/` | **Full Ownership — Industrial OS** | Stays in place |
| `core/models/{energy,manufacturing,water,healthcare,industrial}.py` | **Full Ownership — Industrial OS** | Stays in place |

**Dependencies:** `core/governance/{energy,manufacturing,water,healthcare}_policies.py`

---

### 1.5 Integration OS

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/connectors/` | **Full Ownership — Integration OS** (6 sub-folders) | Stays in place |
| `core/communication_hub/` | **Full Ownership — Integration OS** | Stays in place |
| `core/gateway/` | **Full Ownership — Integration OS** (Provider Gateway) | Stays in place |
| `core/marketplace/` | **Full Ownership — Integration OS** | Stays in place |
| `routers/integrations.py` | **Full Ownership — Integration API** | Stays in place |
| `routers/providers.py` | **Full Ownership — Provider Marketplace API** | Stays in place |
| `core/models/integration.py` | **Full Ownership — Integration OS** | Stays in place |
| `core/models/provider_marketplace.py` | **Full Ownership — Integration OS** | Stays in place |

---

### 1.6 Cognitive Layer

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/cognition/` | **Full Ownership — Cognitive Layer** | Stays in place |
| `core/knowledge_graph/` | **Full Ownership — Cognitive Layer** | Stays in place |
| `core/knowledge_graph_os/` | **Full Ownership — Cognitive Layer** | Stays in place |
| `core/knowledge_os/` | **Full Ownership — Cognitive Layer** | Stays in place |
| `core/workspace_intelligence/` | **Full Ownership — Cognitive Layer** | Stays in place |
| `core/embedding_engine.py` | **Full Ownership — Cognitive Layer** | Stays in place |
| `core/semantic_store.py` | **Full Ownership — Cognitive Layer** | Stays in place |
| `core/graph_query.py` | **Full Ownership — Cognitive Layer** | Stays in place |
| `core/hybrid_retriever.py` | **Full Ownership — Cognitive Layer** | Stays in place |

---

### 1.7 Security Governance

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/security/` | **Full Ownership — Security Governance** | Stays in place |
| `core/governance/` | **Full Ownership — Security Governance** | Stays in place |
| `core/threat_intel/` | **Full Ownership — Security Governance** | Stays in place |
| `core/guardrails.py` | **Full Ownership — Security Governance** | Stays in place |
| `core/models/{security,secrets,trust,safety}.py` | **Full Ownership — Security Governance** | Stays in place |
| `SECURITY.md` | **Full Ownership — Security Governance** | Stays in place |

---

### 1.8 Memory Governance

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/memory/` | **Full Ownership — Memory Governance** (6 files) | Stays in place |
| `core/enterprise_memory/` | **Full Ownership — Memory Governance** | Stays in place |
| `core/data_fabric/` | **Full Ownership — Memory Governance** | Stays in place |
| `core/memory_pressure.py` | **Full Ownership — Memory Governance** | Stays in place |
| `core/execution_memory.py` | **Full Ownership — Memory Governance** | Stays in place |

---

### 1.9 Production Hardening

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/hardening/` | **Full Ownership — Production Hardening** | Stays in place |
| `core/chaos/` | **Full Ownership — Production Hardening** | Stays in place |
| `core/deployment/` | **Full Ownership — Production Hardening** | Stays in place |
| `core/release/` | **Full Ownership — Production Hardening** | Stays in place |
| `core/readiness/` | **Full Ownership — Production Hardening** | Stays in place |
| `core/recovery/` | **Full Ownership — Production Hardening** | Stays in place |
| `core/connector_cert/` | **Full Ownership — Production Hardening** | Stays in place |
| `Dockerfile` | **Full Ownership — Production Hardening** | Stays in place |
| `docker-compose.yml` | **Full Ownership — Production Hardening** | Stays in place |
| `.github/workflows/ci.yml` | **Full Ownership — Production Hardening** | Stays in place |

---

### 1.10 Command Center — Ops / Supervisory Layer

`core/command_center/` is a **Supervisory and Operations Layer**, not the final owner of every API or Router in the system. Its function: monitoring, dashboards, CLI, and operational control.

| Path | Ownership Type | Status |
|------|---------------|--------|
| `core/command_center/` | **Ops / Supervisory Layer** | Stays in place |
| `core/control_plane/` | **Full Ownership — Command Center** | Stays in place |
| `core/observability/` | **Full Ownership — Command Center** | Stays in place |
| `core/cli/` | **Full Ownership — Command Center** | Stays in place |
| `core/service_registry.py` | **Full Ownership — Command Center** | Stays in place |
| `core/worker_registry.py` | **Full Ownership — Command Center** | Stays in place |

---

## 2. Cross-Cutting Components (Not Belonging to a Specific OS Layer)

### 2.1 `core/runtime/` — Execution Substrate

`core/runtime/` is the **execution substrate** — does not belong to any specific OS. All layers depend on it.

| Classification | Value |
|---------------|-------|
| **Ownership** | **Execution Substrate — Independent of all layers** |
| **Status** | Stays in `core/runtime/` as is |
| **Components** | scheduler, state store, dispatcher, retry/lease/recovery, sandbox, isolation, resource scheduling, trust scheduling, event integration, control plane adapters |
| **Beneficiaries** | All ten layers |
| **Dependencies** | `core/models/`, `core/security/` |

**Previous Phase Files:** `core/runtime/unified_api.py` (F1), `core/runtime/control_plane/` (F2), `core/runtime/resource_scheduler/` (F3), `core/runtime/tracing/` (F4)

---

### 2.2 `core/execution_engine.py` — Thin Compatibility Entrypoint

| Classification | Value |
|---------------|-------|
| **Ownership** | **Thin entrypoint** — Not treated as a Domain component |
| **Status** | Stays in place. Future: migrate to `core/runtime/execution_engine.py` in refactor branch |

---

### 2.3 `core/interfaces/` — Service Contracts

| Classification | Value |
|---------------|-------|
| **Ownership** | **Cross-cutting** — All layers |
| **Status** | Stays in place |

---

## 3. `core/models/` — Models (Current State)

`core/models/` currently contains **33 flat model files** belonging to multiple layers. **This is the current structure and is not changed now.**

### Current Division by Content (Classification only — no migration):

| Group | Files |
|-------|-------|
| **Shared** | `event.py`, `events.py`, `failure_propagation.py`, `rollback.py`, `lifecycle.py`, `dag.py`, `types.py` |
| **Agent OS** | `agent.py`, `planner.py`, `critic.py` |
| **Industrial OS** | `energy.py`, `manufacturing.py`, `manufacturing_advanced.py`, `water.py`, `healthcare.py`, `industrial.py`, `energy_policy.py` |
| **Security Governance** | `security.py`, `secrets.py`, `trust.py`, `safety.py`, `guardrails.py` |
| **Integration OS** | `integration.py`, `provider_marketplace.py` |
| **Infrastructure / Runtime** | `infra_models.py`, `runtime_api.py`, `resource_scheduler.py`, `control_plane.py`, `distributed_tracing.py`, `sandbox.py` |
| **Workspace / Observability** | `workspace.py`, `observability.py` |

### Future Refactor Target — `core/models/` split (in independent branch)

> ⚠️ **This is not the current structure.** This is the future target only, to be implemented in a separate `refactor/` branch after Pilot.

```
core/models/
├── shared/          ← event.py, events.py, failure_propagation.py, rollback.py, lifecycle.py, types.py
├── agents/          ← agent.py, planner.py, critic.py
├── industrial/      ← energy.py, manufacturing.py, manufacturing_advanced.py, water.py, healthcare.py, industrial.py
├── security/        ← security.py, secrets.py, trust.py, safety.py, guardrails.py
├── integration/     ← integration.py, provider_marketplace.py
├── infrastructure/  ← infra_models.py, runtime_api.py, resource_scheduler.py, control_plane.py, distributed_tracing.py, sandbox.py
└── workspace/       ← workspace.py, observability.py
```

---

## 4. `routers/` — API Surfaces, Not Domain Ownership

`routers/` are **public API surfaces**, not deep ownership layers. Their classification reflects the domain they serve, not their organizational affiliation.

| Router | Domain | Note |
|--------|--------|------|
| `workflow.py` | Workflow OS | |
| `project.py` | Project OS | |
| `integrations.py` | Integration OS | |
| `providers.py` | Provider Marketplace (Integration OS) | |
| `workspace.py` | Infrastructure (Cross-cutting) | |
| `ai.py` | Agent OS | |
| `chat.py` | Agent OS | |
| `conversations.py` | Agent OS | |
| `history.py` | Memory Governance | |
| `stream.py` | Runtime | |
| `tasks.py` | Runtime | |
| `auth.py` | Security Governance | |
| `e2e.py` | Testing / Production Hardening | |
| `observability.py` | Command Center | |
| `runtime_api.py` | Runtime | |
| `settings.py` | Command Center | |

**Fixed Principle:** `routers/` contain only routing logic (routing, validation, auth). No executive logic (`execute`, `run`, `dispatch`, `sandbox`).

### Future Refactor Target (in independent branch):

```
routers/
├── agents/       ← ai.py, chat.py, conversations.py
├── workflows/    ← workflow.py
├── runtime/      ← stream.py, tasks.py, runtime_api.py
├── security/     ← auth.py
├── enterprise/   ← project.py, workspace.py
├── integrations/ ← integrations.py, providers.py
└── command_center/ ← observability.py, settings.py, history.py
```

---

## 5. `apps/web/` — Presentation Layer

| Classification | Value |
|---------------|-------|
| **Ownership** | **Presentation Layer** — Independent presentation layer |
| **Status** | Stays in place |
| **Platform** | Vercel (Frontend only) — Fully separate from Backend |
| **Strict Rule** | **Forbidden to import any executive logic** from `core/` directly. Communicates with Backend via API calls only. |

---

## 6. `tests/` — Present and Future Tests

### Current State: ~80 flat test files in `tests/`

### Future Refactor Target:

```
tests/
├── agents/
├── runtime/
├── workflows/
├── security/
├── industrial/
├── integration/
├── ui/
├── deployment/
└── core/           ← For cross-cutting components
```

---

## 7. Cross-Cutting Dependency Matrix

| Consumer ↓ / Producer → | `core/runtime/` | `core/security/` | `core/governance/` | `core/models/` | `core/interfaces/` |
|-------------------------|:---:|:---:|:---:|:---:|:---:|
| Agent OS | ✅ | ✅ | ✅ | ✅ | ✅ |
| Workflow OS | ✅ | ✅ | ✅ | ✅ | ✅ |
| Project OS | — | ✅ | ✅ | ✅ | ✅ |
| Industrial OS | — | ✅ | ✅ | ✅ | — |
| Integration OS | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cognitive Layer | ✅ | ✅ | — | ✅ | — |
| Security Governance | ✅ | — | ✅ | ✅ | ✅ |
| Memory Governance | ✅ | ✅ | — | ✅ | — |
| Production Hardening | ✅ | ✅ | ✅ | ✅ | — |
| Command Center | ✅ | ✅ | — | ✅ | ✅ |
| `routers/` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `apps/web/` | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 8. Roadmap — Two Phases

### Phase 1 — Mapping Only (Complete ✅)
- [x] Document current ownership of each folder
- [x] Classify components into ten layers
- [x] Identify dependencies
- [x] Separate current state from future organization
- [x] Document `core/runtime/` as independent execution substrate
- [x] Document `routers/` as API interfaces (not deep ownership)
- [x] Document `apps/web/` as presentation layer
- [x] Confirm freeze of `release/v1-production-candidate`

### Phase 2 — Refactor Branch (Future, After Pilot)
- [ ] Create branch: `refactor/10-layer-architecture`
- [ ] Split `core/models/` according to Future Refactor Target
- [ ] Organize `routers/` by domain
- [ ] Fill `core/workflow_os/` with Workflow-specific content
- [ ] Move `core/execution_engine.py` ← `core/runtime/execution_engine.py` (optional)
- [ ] Organize `tests/` by layer
- [ ] Update all imports
- [ ] Run all tests and verify CI
- [ ] Merge branch after team approval

---

## 9. Guiding Principles

1. **Do not break the public API** — All existing endpoints remain available
2. **Do not break imports** — Symbolic links (symlinks) as transitional phase if necessary
3. **Each Refactor in a separate branch** — Not in `release/` or `main/`
4. **100% of tests pass** before and after Refactor
5. **No functional changes** — Refactor is structural only, no feature addition
6. **Pilot first** — No Refactor before Pilot stabilizes and sufficient data is collected

---

> **Summary:** The system is currently valid for Pilot. All ten layer components exist in `core/` but are not hierarchically organized. This document establishes the actual current state and clearly defines the future refactor target, without mixing the two. The `release/v1-production-candidate` branch is frozen. Refactor will be in a separate branch later after Pilot.
