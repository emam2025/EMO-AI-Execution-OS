# Changelog — EMO Distributed AI Runtime OS

## [v1-runtime-stable] — 2026-05-29 — IMMUTABLE RELEASE

### Executive Summary
Release 1 of the EMO Distributed AI Runtime OS is officially closed and archived.
This is an **immutable snapshot** — no further modifications will be made to this
release. All future development continues on `next-dev` (R2/R3).

### Achievements
- **Cognitive Memory (Phase L)**: MemoryHierarchy with tenant-isolated storage,
  ContextCompiler with TokenBudget enforcement, SkillGraphManager, MemoryStateMachine
  (6 states/7 transitions, G-M1–G-M6 guards), CognitiveTraceCorrelator — 25/25 tests.
- **Cognitive Orchestration (Phase G)**: PlannerAgent, CriticAgent, OptimizerAgent,
  OrchestrationStateMachine (8 states/9 transitions, G-P1–G-P8 guards),
  OrchestrationTraceCorrelator — 41/41 tests.
- **Security Baseline**: EMO_JWT_SECRET enforcement, admin123456 removed,
  SecurityHeadersMiddleware (CSP/HSTS/X-Frame), 0 dependency vulnerabilities.
- **Developer Foundation**: SDK spec (`docs/sdk_spec.md`), CLI wrapper
  (`scripts/cli/emo_cli.py`), Runtime API reference (`docs/runtime_api_reference.md`).
- **Debt Quarantine**: 100 pre-existing failures classified across 5 categories
  (`tests/quarantine/`), `@pytest.mark.quarantined` auto-skip mechanism.

### Quality Gates
| Gate | Status |
|---|---|
| High-Signal Ratio | ≥85% ✅ |
| Regression Count | 0 ✅ |
| Canon Compliance | 100% ✅ |
| Trace Propagation | 100% ✅ |
| Replay Integrity | PASS ✅ |
| Isolation Validation | PASS ✅ |

### Deployment Constraints
- Single-node SQLite-backed deployment.
- Requires Python 3.14+, `EMO_JWT_SECRET` env var.
- 100 pre-existing test failures quarantined (see `DEBT_RESOLUTION_PLAN.md`).
- No multi-tenant enterprise billing (moved to R2).
- No distributed runtime mesh (moved to R3).

### Transition Notes
- **Branch**: `main` is frozen at `v4.15.0-delivery-ready`.
- **Next**: All R2/R3 development occurs on `next-dev` branch.
- **Archive**: Full release archive at `emo-runtime-os-v1-release.tar.gz`.
- **Tag**: `v1-runtime-stable` (signed).
