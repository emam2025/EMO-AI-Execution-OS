# EMO AI Execution OS — Repository Structure Map

**Version:** 1.0.0-RC18
**Tag:** `v1.0.0-RC18-BASELINE`
**Generated:** 2026-06-22

---

## Layer Architecture

```
Industrial Layer    │ core/industrial/, core/connectors/
Platform Layer      │ core/composition/, core/observability/, core/recovery/, routers/, templates/, static/
Governance Layer    │ core/governance/, core/security/, core/guardrails.py, middleware/
Memory Layer        │ core/memory/, core/semantic_store.py
Automation Layer    │ core/execution_engine.py, core/workflow_runtime_v2/
Intelligence Layer  │ core/agents/, core/orchestration/, core/codegraph/, brain.py, agent.py
Kernel Layer        │ core/canon/, core/interfaces/, core/models/, core/runtime/, tools.py
```

---

## Top-Level Directories

| Directory | Purpose | Architecture Layer | Owner | Dependencies | Forbidden Imports |
|-----------|---------|-------------------|-------|--------------|-------------------|
| `core/` | System kernel — runtime, agents, governance, security, industrial | All layers | core team | All `core/` submodules | `routers/`, `frontend/`, `apps/` |
| `routers/` | FastAPI HTTP endpoint definitions (18 routers) | Platform (API) | core team | `core/`, `middleware/`, `brain.py` | `frontend/`, `apps/`, `emo-desktop/` |
| `middleware/` | Auth middleware (JWT, RBAC) | Governance | core team | `core/security/`, FastAPI | `routers/`, `frontend/` |
| `templates/` | Jinja2 HTML templates (dashboard, panels) | Platform (UI) | core team | FastAPI Jinja2Templates | No Python imports |
| `static/` | Static web assets (CSS, logo) | Platform (UI) | core team | Served by FastAPI | — |
| `apps/web/` | Next.js web application | Platform (UI) | core team | Next.js, React | `core/` (uses HTTP API) |
| `frontend/minimal/` | Minimal standalone frontend | Platform (UI) | core team | Python, HTML | `core/` (uses API) |
| `emo-desktop/` | Tauri desktop application | Platform (Desktop) | core team | Tauri (Rust), Vite | `core/` (uses HTTP/IPC) |
| `tests/` | 239+ test files across all layers | Non-core (Testing) | core team | All modules | Tests may import anything; production must not import tests |
| `docs/` | Architecture, deployment, pilot, release docs | Non-core (Docs) | core team | — | — |
| `scripts/` | Build, audit, release, validation scripts | Non-core (DevOps) | core team | Shell, Python stdlib | — |
| `audit/` | Reality checks, architecture audit reports | Non-core (Audit) | core team | Project modules (read-only) | Must not be imported by production |
| `releases/` | Archived release snapshots and certificates | Non-core (Release) | core team | — | Must not be imported by production |
| `artifacts/` | Build outputs, validation data, certifications | Non-core (Artifacts) | core team | — | Must not be imported by production |
| `.github/` | CI/CD, issue templates, PR template, CODEOWNERS | Non-core (CI/CD) | core team | GitHub Actions | — |
| `.opencode/` | OpenCode AI agents and skills | Non-core (Dev) | core team | OpenCode | — |
| `.githooks/` | Pre-commit hooks | Non-core (Git) | core team | Shell | — |
| `.ai/` | AI code intelligence data (cache, embeddings, graphs) | Intelligence (AI Data) | core team | `core/ai_agent.py` | Data only — not committed |
| `simulation_lab/` | Reserved for industrial simulation testing | Non-core (Sim) | core team | — | — |
| `test-projects/` | External test project fixtures | Non-core (Testing) | core team | — | — |
| `logo/` | Brand logo assets | Non-core (Brand) | core team | — | — |
| `RELEASE_NOTES/` | Release notes per version | Non-core (Docs) | core team | — | — |

---

## `core/` Subdirectories

| Directory | Purpose | Layer | Owner | Dependencies | Forbidden Imports |
|-----------|---------|-------|-------|--------------|-------------------|
| `core/canon/` | LAW 1-27 / RULE 1-10 architectural rules engine | Kernel (Layer 1) | core team | None (foundation) | All other layers |
| `core/interfaces/` | Protocol/interface definitions (29 modules) — D8 Service Mesh contracts | Kernel (Contracts) | core team | `core/models/` | Any implementation (`core/runtime/`, etc.) |
| `core/models/` | Pydantic data models (32 modules) — DAG, agent, event, sector models | Kernel (Data) | core team | Pydantic | Any business logic module |
| `core/runtime/` | Core runtime engine (44 entries) — bootstrap, event bus, scheduler, sandbox, tool synthesis, mesh | Kernel (Runtime) | core team | `core/interfaces/`, `core/models/`, `core/canon/` | `routers/`, `frontend/`, `brain.py`, `agent.py` |
| `core/agents/` | Agent implementations — planner, critic, adaptive, lifecycle, sector agents | Intelligence | core team | `core/models/`, `core/interfaces/`, `core/governance/`, `brain.py` | `routers/`, `frontend/` |
| `core/orchestration/` | Multi-agent orchestration — critic, optimizer, planner agents, state machine | Intelligence | core team | `core/interfaces/`, `core/runtime/`, `core/agents/` | `frontend/`, `apps/` |
| `core/codegraph/` | Code intelligence engine — analyzer, DAG builder, query engine, drift detection | Intelligence | core team | `core/models/dag.py`, `core/interfaces/` | `routers/`, `frontend/`, `core/industrial/` |
| `core/memory/` | Memory subsystem — context compilation, hierarchy, state machine, skill graph | Memory | core team | `core/models/`, `core/interfaces/state_store.py` | `routers/`, `frontend/`, `core/execution_engine.py` |
| `core/governance/` | Governance and policies — RBAC, audit, guardrails, sector policies, rollback | Governance | core team | `core/security/`, `core/models/` | `routers/`, `frontend/`, `core/industrial/` |
| `core/security/` | Security primitives — keychain, RBAC, identity, capability guard, secrets runtime | Governance | core team | `core/interfaces/security.py`, `core/canon/` | `routers/`, `frontend/`, `core/industrial/`, `core/agents/` |
| `core/industrial/` | Digital twins and industrial logic — OEE engine, sector data pipelines, twin manager | Industrial | core team | `core/models/`, `core/governance/`, `core/connectors/` | `frontend/`, `apps/`, `brain.py`, `agent.py` |
| `core/connectors/` | External system connectors — energy, healthcare, manufacturing, water, communication | Industrial | core team | `core/interfaces/connectors.py`, `core/models/integration.py` | `routers/`, `frontend/`, `brain.py`, `agent.py` |
| `core/observability/` | Telemetry, metrics, tracing, DAG visualization, topology viewer | Platform | core team | `core/interfaces/observability.py`, `core/runtime/tracing/` | `frontend/`, `apps/`, `core/industrial/` |
| `core/composition/` | DI composition root — dependency injection wiring | Platform | core team | All `core/` modules | Only place for DI wiring |
| `core/recovery/` | System recovery, replay, resilience | Platform | core team | `core/interfaces/`, `core/runtime/` | `frontend/`, `apps/` |

---

## Key Top-Level Files

| File | Purpose | Layer | Dependencies |
|------|---------|-------|--------------|
| `main.py` | FastAPI entrypoint — lifespan, router registration, security middleware | Platform | `brain.py`, `core/`, `routers/`, `middleware/` |
| `brain.py` | LLM interface — 4 providers (OpenRouter, Groq, Gemini, Ollama) | Intelligence | `openai`, `httpx`, `core/security/keychain_provider` |
| `agent.py` | Role-based agent class (planner, coder, writer, researcher) | Intelligence | `brain.py`, `core/tool_executor` |
| `tray.py` | Cross-platform system tray application | Platform | `pystray`, `Pillow`, `psutil` |
| `tools.py` | Abstract Tool base class and Registry | Kernel | None (pure abstract) |
| `setup.py` | Project setup and installation script | Non-core (DevOps) | `subprocess`, `shutil` |
| `memory.py` | Standalone memory utilities | Memory | — |
| `Dockerfile` | Backend Docker build | Non-core (Deploy) | `requirements.txt` |
| `docker-compose.yml` | Docker Compose (backend + web) | Non-core (Deploy) | `Dockerfile`, `apps/web/Dockerfile` |
| `railway.toml` | Railway.app deployment config | Non-core (Deploy) | `Dockerfile` |
| `pytest.ini` | Pytest configuration | Non-core (Testing) | pytest |
| `VERSION` | Current version: `1.0.0-RC18` | Non-core (Version) | — |
| `requirements.txt` | Python dependencies | Non-core (Deps) | pip |
| `opencode.jsonc` | OpenCode configuration | Non-core (Dev) | OpenCode |

---

## Layer Dependency Diagram

```
Kernel (canon, interfaces, models)
  ↑
Intelligence (agents, orchestration, codegraph, brain)
  ↑
Automation (execution_engine, workflow)
  ↑
Memory (memory, semantic_store)
  ↑
Governance (governance, security, guardrails)
  ↑
Platform (composition, observability, recovery, routers, templates)
  ↑
Industrial (industrial, connectors)
```

- Dependencies flow **upward** (Kernel has zero dependencies on upper layers)
- Cross-layer imports are **forbidden** (enforced by canon rules)
- `core/interfaces/` must never import from `core/runtime/` or any implementation
- `core/canon/` must never import from any other layer

---

## Directory Size & Composition

| Directory | Entry Count | Notes |
|-----------|-------------|-------|
| `core/` | ~120 | Heart of the system |
| `tests/` | ~239 | 1667+ individual tests |
| `docs/` | 36 | Documentation files |
| `scripts/` | ~20 | Build and automation |
| `releases/` | ~40 | Archived release artifacts |
| `artifacts/` | ~30 | Build outputs |
| `emo-desktop/` | ~50 | Tauri desktop app |
| `apps/web/` | ~25 | Next.js web app |

---

## Ownership Summary

| Area | Owner |
|------|-------|
| Kernel runtime, interfaces, models | core team |
| Intelligence, agents, orchestration | core team |
| Workflow, execution engine | core team |
| Memory, knowledge systems | core team |
| Governance, security, RBAC | core team |
| Industrial, connectors, digital twins | core team |
| Platform, API, observability | core team |
| Tests | core team (all contributors) |
| CI/CD, deployment | core team |
| Documentation | core team (all contributors) |

---

**See also:**
- [SOURCE_OF_TRUTH.md](SOURCE_OF_TRUTH.md) — Trust hierarchy and documentation policy
- [EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md](EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md) — Canonical engineering reference
