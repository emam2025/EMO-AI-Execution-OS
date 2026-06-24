# Architecture Ownership Map — Emo-AI

> **Purpose:** Document the ownership of each directory, classify its affiliation with the ten layers (current and future), identify dependencies, and separate what exists now from what will be migrated later.
>
> **Branch status:** `release/v1-production-candidate` — **Frozen**. No changes until the end of the Pilot.
>
> **Document type:** Mapping Only — not an executable Refactor plan.

---

## 1. The Ten Layers — Present and Future Ownership

### 1.1 Agent OS

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/agents/` | **Full ownership — Agent OS** | Remains in place |
| `core/agent_teams/` | **Full ownership — Agent OS** | Remains in place |
| `core/planner/` | **Full ownership — Agent OS** | Remains in place |
| `core/autonomous_control/` | **Full ownership — Agent OS** | Remains in place |
| `core/autonomy/` | **Full ownership — Agent OS** | Remains in place |

**Core files:** `core/agents/planner_agent.py`, `critic_agent.py`, `adaptive_planner.py`, the sector directories under `core/agents/{energy,manufacturing,water,healthcare}/`.

**Dependencies:** `core/models/` (event, planner, critic, agent), `core/interfaces/`, `core/governance/`, `core/security/`

---

### 1.2 Workflow OS

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/workflow_os/` | **Reserved / Target Ownership** — future container for Workflow content | **Exists but currently empty** (contains only `__pycache__`). Will be populated later |
| `core/workflow_runtime_v2/` | **Full ownership — Workflow OS** | Remains in place |
| `core/canvas/` | **Subordinate ownership — Workflow OS** (UI canvas) | Remains in place |
| `core/dag_*.py` | **Full ownership — Workflow OS** | Remains in place |
| `routers/workflow.py` | **Full ownership — Workflow API** | Remains in place |

**Proposed future content of `core/workflow_os/` (in a refactor branch):**
- `workflow_engine.py` — DAG engine
- `workflow_validator.py` — DAG validation (currently in `routers/workflow.py`)
- `workflow_scheduler.py` — workflow scheduling
- `workflow_models.py` — Workflow-specific models

**Dependencies:** `core/models/dag.py`, `core/models/event.py`, `core/runtime/`

---

### 1.3 Project OS

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/projectos/` | **Full ownership — Project OS** | Remains in place |
| `routers/project.py` | **Full ownership — Project API** | Remains in place |

**Dependencies:** `core/models/`, `core/security/`, `core/governance/`

---

### 1.4 Industrial OS

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/industrial/` | **Full ownership — Industrial OS** | Remains in place |
| `core/industry_profiles/` | **Full ownership — Industrial OS** | Remains in place |
| `core/digital_twin_v2/` | **Full ownership — Industrial OS** | Remains in place |
| `core/models/{energy,manufacturing,water,healthcare,industrial}.py` | **Full ownership — Industrial OS** | Remains in place |

**Dependencies:** `core/governance/{energy,manufacturing,water,healthcare}_policies.py`

---

### 1.5 Integration OS

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/connectors/` | **Full ownership — Integration OS** (6 subdirectories) | Remains in place |
| `core/communication_hub/` | **Full ownership — Integration OS** | Remains in place |
| `core/gateway/` | **Full ownership — Integration OS** (Provider Gateway) | Remains in place |
| `core/marketplace/` | **Full ownership — Integration OS** | Remains in place |
| `routers/integrations.py` | **Full ownership — Integration API** | Remains in place |
| `routers/providers.py` | **Full ownership — Provider Marketplace API** | Remains in place |
| `core/models/integration.py` | **Full ownership — Integration OS** | Remains in place |
| `core/models/provider_marketplace.py` | **Full ownership — Integration OS** | Remains in place |

---

### 1.6 Cognitive Layer

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/cognition/` | **Full ownership — Cognitive Layer** | Remains in place |
| `core/knowledge_graph/` | **Full ownership — Cognitive Layer** | Remains in place |
| `core/knowledge_graph_os/` | **Full ownership — Cognitive Layer** | Remains in place |
| `core/knowledge_os/` | **Full ownership — Cognitive Layer** | Remains in place |
| `core/workspace_intelligence/` | **Full ownership — Cognitive Layer** | Remains in place |
| `core/embedding_engine.py` | **Full ownership — Cognitive Layer** | Remains in place |
| `core/semantic_store.py` | **Full ownership — Cognitive Layer** | Remains in place |
| `core/graph_query.py` | **Full ownership — Cognitive Layer** | Remains in place |
| `core/hybrid_retriever.py` | **Full ownership — Cognitive Layer** | Remains in place |

---

### 1.7 Security Governance

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/security/` | **Full ownership — Security Governance** | Remains in place |
| `core/governance/` | **Full ownership — Security Governance** | Remains in place |
| `core/threat_intel/` | **Full ownership — Security Governance** | Remains in place |
| `core/guardrails.py` | **Full ownership — Security Governance** | Remains in place |
| `core/models/{security,secrets,trust,safety}.py` | **Full ownership — Security Governance** | Remains in place |
| `SECURITY.md` | **Full ownership — Security Governance** | Remains in place |

---

### 1.8 Memory Governance

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/memory/` | **Full ownership — Memory Governance** (6 files) | Remains in place |
| `core/enterprise_memory/` | **Full ownership — Memory Governance** | Remains in place |
| `core/data_fabric/` | **Full ownership — Memory Governance** | Remains in place |
| `core/memory_pressure.py` | **Full ownership — Memory Governance** | Remains in place |
| `core/execution_memory.py` | **Full ownership — Memory Governance** | Remains in place |

---

### 1.9 Production Hardening

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/hardening/` | **Full ownership — Production Hardening** | Remains in place |
| `core/chaos/` | **Full ownership — Production Hardening** | Remains in place |
| `core/deployment/` | **Full ownership — Production Hardening** | Remains in place |
| `core/release/` | **Full ownership — Production Hardening** | Remains in place |
| `core/readiness/` | **Full ownership — Production Hardening** | Remains in place |
| `core/recovery/` | **Full ownership — Production Hardening** | Remains in place |
| `core/connector_cert/` | **Full ownership — Production Hardening** | Remains in place |
| `Dockerfile` | **Full ownership — Production Hardening** | Remains in place |
| `docker-compose.yml` | **Full ownership — Production Hardening** | Remains in place |
| `.github/workflows/ci.yml` | **Full ownership — Production Hardening** | Remains in place |

---

### 1.10 Command Center — Ops / Supervisory Layer

`core/command_center/` is a **Supervisory Layer**, not the ultimate owner of every API or Router in the system. Its function: monitoring, dashboards, CLI, and operational control.

| Path | Ownership Type | Status |
|--------|------------|--------|
| `core/command_center/` | **Ops / Supervisory Layer** | Remains in place |
| `core/control_plane/` | **Full ownership — Command Center** | Remains in place |
| `core/observability/` | **Full ownership — Command Center** | Remains in place |
| `core/cli/` | **Full ownership — Command Center** | Remains in place |
| `core/service_registry.py` | **Full ownership — Command Center** | Remains in place |
| `core/worker_registry.py` | **Full ownership — Command Center** | Remains in place |

---

## 2. Cross-Cutting Components (do not belong to a specific OS layer)

### 2.1 `core/runtime/` — Execution Substrate

`core/runtime/` is the **execution substrate** — it does not belong to any specific OS. All layers depend on it.

| Classification | Value |
|---------|--------|
| **Ownership** | **Execution Substrate — independent of all layers** |
| **Status** | Remains in `core/runtime/` as-is |
| **Components** | scheduler, state store, dispatcher, retry/lease/recovery, sandbox, isolation, resource scheduling, trust scheduling, event integration, control plane adapters |
| **Consumers** | All ten layers |
| **Dependencies** | `core/models/`, `core/security/` |

**Previous Phases files:** `core/runtime/unified_api.py` (F1), `core/runtime/control_plane/` (F2), `core/runtime/resource_scheduler/` (F3), `core/runtime/observability/` (F4)

---

### 2.2 `core/execution_engine.py` — Thin Compatibility Entrypoint

| Classification | Value |
|---------|--------|
| **Ownership** | **Thin entrypoint** — not treated as a Domain component |
| **Status** | Remains in place. In the future it will be migrated to `core/runtime/execution_engine.py` in a refactor branch |

---

### 2.3 `core/interfaces/` — Service Contracts

| Classification | Value |
|---------|--------|
| **Ownership** | **Cross-cutting** — all layers |
| **Status** | Remains in place |

---

## 3. `core/models/` — Models (Current State)

`core/models/` currently contains **33 flat model files** belonging to multiple layers. **This is the current structure and will not be changed now.**

### Current grouping by content (classification only — no migration):

| Group | Files |
|----------|---------|
| **Shared** | `event.py`, `events.py`, `failure_propagation.py`, `rollback.py`, `lifecycle.py`, `dag.py`, `types.py` |
| **Agent OS** | `agent.py`, `planner.py`, `critic.py` |
| **Industrial OS** | `energy.py`, `manufacturing.py`, `manufacturing_advanced.py`, `water.py`, `healthcare.py`, `industrial.py`, `energy_policy.py` |
| **Security Governance** | `security.py`, `secrets.py`, `trust.py`, `safety.py`, `guardrails.py` |
| **Integration OS** | `integration.py`, `provider_marketplace.py` |
| **Infrastructure / Runtime** | `infra_models.py`, `runtime_api.py`, `resource_scheduler.py`, `control_plane.py`, `distributed_tracing.py`, `sandbox.py` |
| **Workspace / Observability** | `workspace.py`, `observability.py` |

### Future Refactor Target — split `core/models/` (in a separate branch)

> ⚠️ **This is not the current structure.** This is only the future target, to be implemented in a separate `refactor/` branch after the Pilot.

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

`routers/` are **public API surfaces**, not deep ownership of the layers. Their classification reflects the domain they serve, not their organizational affiliation.

| Router | Domain | Note |
|---------|--------|--------|
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

**Fixed principle:** `routers/` contains only routing logic (routing, validation, auth). It does not contain execution logic (`execute`, `run`, `dispatch`, `sandbox`).

### Future Refactor Target (in a separate branch):

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
|---------|--------|
| **Ownership** | **Presentation Layer** — independent presentation layer |
| **Status** | Remains in place |
| **Platform** | Vercel (Frontend only) — completely separate from Backend |
| **Strict rule** | **Importing any execution logic** from `core/` directly is prohibited. It communicates with the Backend via API calls only. |

---

## 6. `tests/` — Present and Future Tests

### Current state: ~80 test files in flat `tests/`

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
└── core/           ← for cross-cutting components
```

---

## 7. Cross-Cutting Dependencies Matrix

| Consumer ↓ / Producer → | `core/runtime/` | `core/security/` | `core/governance/` | `core/models/` | `core/interfaces/` |
|----------------------|:---:|:---:|:---:|:---:|:---:|
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

### Phase 1 — Mapping Only (Completed ✅)
- [x] Document current ownership for each directory
- [x] Classify components into the ten layers
- [x] Identify dependencies
- [x] Separate current state from future organization
- [x] Document `core/runtime/` as an independent execution substrate
- [x] Document `routers/` as API surfaces (not deep ownership)
- [x] Document `apps/web/` as a presentation layer
- [x] Confirm freezing of `release/v1-production-candidate`

### Phase 2 — Refactor Branch (future, after Pilot)
- [ ] Create branch: `refactor/10-layer-architecture`
- [ ] Split `core/models/` per the Future Refactor Target
- [ ] Organize `routers/` by domain
- [ ] Populate `core/workflow_os/` with Workflow-specific content
- [ ] Move `core/execution_engine.py` ← `core/runtime/execution_engine.py` (optional)
- [ ] Organize `tests/` by layer
- [ ] Update all imports
- [ ] Run all tests and verify CI
- [ ] Merge the branch after team approval

---

## 9. Guiding Principles

1. **Do not break the public API** — all existing endpoints remain available
2. **Do not break imports** — symbolic links (symlinks) as a transitional step if needed
3. **Every Refactor in a separate branch** — not in `release/` or `main/`
4. **100% of tests pass** before and after the Refactor
5. **No functional changes** — the Refactor is structural only, no feature additions
6. **Pilot first** — no Refactor before the Pilot stabilizes and sufficient data is collected

---

> **Conclusion:** The system is currently Pilot-ready. All components of the ten layers exist in `core/` but are not organized hierarchically. This document captures the actual reality (current state) and clearly defines the future target (future refactor target), without conflating the two. The `release/v1-production-candidate` branch is frozen. The Refactor will take place in a separate branch later, after the Pilot.
