# EMO AI — Developer Reference Guide

| Field | Value |
|------|-------|
| **Version** | 1.0.0-RC18 |
| **Last Updated** | 2026-06-24 |
| **Status** | Active |
| **Branch** | `develop` |

---

## Overview

This document is the canonical developer reference for EMO AI Execution OS. It covers Canon Laws, development rules, architecture layers, and contribution guidelines.

---

## Canon Laws (LAW 1-27)

The project enforces 27 architectural laws. Key laws:

### Core Laws

| Law | Title | Description |
|-----|-------|-------------|
| LAW 1 | Single Source of Truth | Code > Tests > VERSION > Tags > Reports > Historical Docs |
| LAW 2 | Interfaces Never Import Implementations | `core/interfaces/` must not import from `core/runtime/` |
| LAW 5 | No Unregistered Debt | All architectural deviations must be in `ACCEPTED_ARCHITECTURAL_DEBT.md` |
| LAW 6 | Shared Models | All dataclasses live in `core/models/` |
| LAW 10 | No Business Logic in Models | Models are data-only; logic lives in services |
| LAW 11 | No Global Mutable State | Use class-based state with proper encapsulation |
| LAW 12 | Trace Propagation | All operations propagate `cognitive_trace_id` |
| LAW 13 | Dependency Injection | All dependencies via constructor, no globals |
| LAW 18 | Trace Analysis Determinism | Trace analysis must be deterministic |
| LAW 23-27 | Service Mesh Ownership | Mesh runtime, registry, protocol ownership rules |

### Enforcement

- `emo-guard` (LAW 13 check) runs pre-commit
- CI gates verify no `NotImplementedError` in `core/`
- Canon freeze test prevents forbidden imports

---

## Architecture Layers

The system has 10 owned layers:

```
1. Kernel Layer          — Execution Runtime, State Machine, Scheduler, Recovery, Replay, Events
2. Intelligence Layer    — Agent OS, Planner, Critic, Optimizer, Multi-Agent Swarm
3. Automation Layer      — Workflow OS, Tool Runtime, Tool Synthesis, Computer Use
4. Memory Layer          — Hierarchy, Semantic Retrieval, Skill Graph, Context Management
5. Governance Layer      — Identity, RBAC, Policy Engine, Audit, Compliance
6. Security Layer        — Capability Guard, IO Policy, Secrets Runtime, Rate Limiting
7. Platform Layer        — Control Plane, Resource Scheduler, Observability
8. Industrial Layer      — Digital Twins, OPC-UA, Modbus, SCADA, Industry Packs
9. Cognitive Layer       — Strategic Planning, Reflection Loops, Adaptive Policies
10. Enterprise Layer     — Multi-tenancy, Billing, Trace Correlation, Compliance
```

### Layer Ownership Rules

- Every component belongs to exactly one layer
- No direct modification of `core/` runtime without Canon LAW 13 audit
- No duplicate implementations
- Every new feature must belong to an existing layer

---

## Development Rules

### Required for Every Change

1. **Layer Verification** — Component belongs to a defined layer
2. **Tests** — All new features require tests in `tests/`
3. **Audit Trail** — Integration with `core/governance/audit_trail.py`
4. **Documentation** — Update CHANGELOG.md + relevant docs
5. **Canon Compliance** — No LAW violations

### Prohibited

- ❌ Adding features outside defined layers
- ❌ Direct modification to `core/` without Canon LAW 13 audit
- ❌ Creating duplicate systems
- ❌ Hardcoded secrets in source code
- ❌ `NotImplementedError` in `core/` (use ABC + `@abstractmethod`)
- ❌ Global mutable state (LAW 11)
- ❌ Business logic in models (LAW 10)

---

## Branch Strategy

### Branches

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready releases |
| `develop` | Active development (default) |
| `release/v1-production-candidate` | Frozen release candidate |
| `feat/*` | Feature branches |
| `fix/*` | Bug fixes |
| `chore/*` | Maintenance |

### Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat` — New feature
- `fix` — Bug fix
- `chore` — Maintenance
- `ci` — CI/CD changes
- `docs` — Documentation
- `refactor` — Code refactoring
- `test` — Tests

**Examples:**
```
feat(memory): implement Project Memory with 75 tests (T-30)
fix(scheduler): add active_assignments property (T-24)
docs(changelog): add T-30 entry [Unreleased]
```

---

## Testing

### Test Structure

```
tests/
├── unit/           — Unit tests
├── integration/    — Integration tests
├── e2e/            — End-to-end tests
├── chaos/          — Chaos engineering
├── load/           — Load tests
├── security/       — Security tests
└── cognitive/      — Cognitive protocol tests
```

### Running Tests

```bash
# Full suite
pytest tests/ -q

# Specific module
pytest tests/test_project_memory.py -v

# With coverage
pytest tests/ --cov=core --cov-report=html

# Collect only (count)
pytest tests/ --collect-only -q | tail -1
```

### Test Requirements

- Every feature requires tests
- No assertionless tests (use `scripts/find_assertionless_tests.py`)
- Critical paths require E2E tests
- Security features require dedicated security tests

---

## Source of Truth Policy

All documentation must follow this priority:

1. **Current repository source code** (highest)
2. **Automated tests**
3. **VERSION and release tags**
4. **Deployment reports**
5. **Previous architecture documents** (lowest)

Historical documents are references only and must not override repository reality.

### Evidence-Based Verification

Every claim must be verifiable:

```bash
# Test count
pytest tests/ --collect-only -q | tail -1

# No NotImplementedError
grep -rn "raise NotImplementedError" core/ --include="*.py" | wc -l

# No hardcoded secrets
grep -rnE "(password|secret|api_key)\s*=\s*['\"][^'\"]{8,}['\"]" core/

# Canon compliance
python3 -m pytest tests/test_canon_freeze.py -v
```

---

## Security

### Principles

1. **Default Deny** — All operations denied unless explicitly allowed
2. **Human-in-the-Loop** — Destructive actions require approval
3. **Audit First** — Every action logged before execution
4. **Raw Evidence Only** — All claims backed by terminal output

### Secrets Management

- Never commit `.env` files, API keys, or credentials
- Use `.env.example` for documentation (empty values only)
- Rotate keys immediately if exposed
- Use `core/security/secrets_runtime.py` for runtime secret injection

### Security Modules

| Module | Path | Purpose |
|--------|------|---------|
| Identity | `core/security/identity.py` | User identity management |
| RBAC | `core/security/rbac.py` | Role-based access control |
| Capability Guard | `core/security/capabilities/` | Tool capability enforcement |
| IO Policy | `core/security/io_policy_engine.py` | Filesystem + network access control |
| Keychain | `core/security/keychain_provider.py` | OS-level secret storage |
| Rate Limiter | `core/rate_limiter.py` | API rate limiting |

---

## Industrial Sector Plugin Model

To add a new industrial sector:

```
EMO Core
│
├── Industry Pack        core/industrial/ + core/governance/{sector}_policies.py
├── Connector            core/connectors/{sector}/
├── Digital Twin         core/industrial/{sector}_twin.py
└── Sector Agents        core/agents/{sector}/
```

### Steps

1. Create `core/connectors/{sector}/` with protocol implementations
2. Create `core/industrial/{sector}_twin.py` with twin model (extend `BaseSectorTwin`)
3. Create `core/governance/{sector}_policies.py` with safety rules
4. Create `core/agents/{sector}/` with sector-specific agents
5. Add tests for each component

---

## Memory OS Architecture

### Components

| Component | Path | Status |
|-----------|------|--------|
| Memory Hierarchy | `core/memory/memory_hierarchy.py` | ✅ Implemented |
| Context Compiler | `core/memory/context_compiler.py` | ✅ Implemented |
| Skill Graph | `core/memory/skill_graph_manager.py` | ✅ Implemented |
| Memory State Machine | `core/memory/memory_state_machine.py` | ✅ Implemented |
| Cognitive Trace Correlator | `core/memory/trace_correlator.py` | ✅ Implemented |
| Project Memory | `core/memory/project_memory.py` | ✅ Implemented (T-30) |
| Agent Memory | `core/memory/agent_memory.py` | ✅ Implemented (T-31) |
| Long-Term Memory | `core/memory/long_term_memory.py` | ✅ Implemented (T-32) |
| Knowledge Graph | — | ⏳ Planned (T-33) |
| Vector DB Backend | `core/vector_db.py` | ✅ Implemented |

### Memory Layers

```python
class MemoryLayer(Enum):
    WORKING = "working"        # Current task state
    SHORT_TERM = "short_term"  # Session context
    LONG_TERM = "long_term"    # Accumulated knowledge
    ARCHIVAL = "archival"      # Cold storage
    PROJECT = "project"        # Per-project namespace (T-30)
```

---

## Maintenance Rules

### Branch Rules

- `release/v1-production-candidate` is **frozen** — no feature changes, wiring fixes only
- All new development on feature branches
- `emo-guard` (LAW 13 check) runs pre-commit

### Release Audit Checklist

Before any release:

| Category | Check | Verification |
|----------|-------|-------------|
| Security | Identity | `core/security/identity.py` |
| Security | RBAC | `core/security/rbac.py` |
| Security | Policy Engine | `core/governance/guardrails_engine.py` |
| Runtime | All Tests Pass | `pytest tests/` |
| Runtime | Recovery Paths | `core/recovery/` |
| Industrial | Safety Gates | `core/governance/safety_gate.py` |
| Industrial | Approval Gates | `core/runtime/autonomy/approval_gate.py` |
| Performance | Latency p95 < 100ms | Requires Railway Pro tier |
| Observability | Telemetry Active | `core/runtime/observability/` |
| Observability | Audit Trail | `core/governance/audit_trail.py` |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines.

### Quick Summary

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make changes following Canon Laws
4. Add tests for all changes
5. Run: `pytest tests/ -q` (must pass with 0 failures)
6. Commit with Conventional Commits format
7. Open a Pull Request with verification output

---

## References

- [Master Architecture Reference](docs/EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md)
- [Development Plan](EMO_AI_DEVELOPMENT_PLAN.md)
- [Architecture Ownership Map](docs/ARCHITECTURE_OWNERSHIP_MAP.md)
- [Accepted Architectural Debt](docs/ACCEPTED_ARCHITECTURAL_DEBT.md)
- [Changelog](CHANGELOG.md)
- [Security Policy](SECURITY.md)
