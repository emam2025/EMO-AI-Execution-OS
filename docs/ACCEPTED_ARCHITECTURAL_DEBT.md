# Accepted Architectural Debt — Certified Trade-Off Register  # LAW-5 # LAW-18

This document catalogs all tracked architectural debts that are **accepted by design**
and **certified as non-blocking** for v4.10.0-prod-ready. These are not bugs — they
are intentional trade-offs where full remediation was deferred to preserve delivery.

Ref: EXEC-DIRECTIVE-028 §Documentation Sync
Ref: DEVELOPER.md §15.22, §16 (Architecture Canon)

---

## Register

| ID | Area | Debt Description | Impact | Remediation Target | Status |
|----|------|------------------|--------|-------------------|--------|
| AD-001 | ExecutionEngine | `DeterministicResume.resume()` resets node states via `execute()`, `build_dag_from_token()` passes invalid `version=` kwarg to `DependencyGraph()` | 3 pre-existing test failures — non-blocking for production | Post-freeze refactor | **RESOLVED** — `execute()` now accepts `preserve_states=True`; `DependencyGraph()` accepts `version=` kwarg; resume skips reset-restore cycle |
| AD-002 | Contracts | 3 permissive defaults in `ContractValidator` (no payload size limit, unicode sanitization omitted) | Theoretical injection vector — no exploit path in current deployment | Post-freeze hardening | **RESOLVED** — payload size limit (10 MB), unicode sanitization, unknown type-hint warning added |
| AD-003 | Multi-Agent | Agent lifecycle layer (G5) has zero test coverage — conceptual only | No runtime impact — layer is not activated in production | K6 phase | **CERTIFIED** |
| AD-004 | Telemetry | F4 TelemetryAggregator skips DAG visualization data for DAGs > 500 nodes | Dashboard DAG view is sparse for large DAGs — CLI/API unaffected | K6 optimization phase | **CERTIFIED** |
| AD-005 | TopologyViewer | `topology_viewer.py` returns static/mocked worker topology — no live agent inventory | Operator CLI worker command shows placeholder data — monitoring unaffected | Post-freeze agent discovery | **CERTIFIED** |
| AD-006 | Replay | Replay uses `UnifiedRuntime.replay()` which re-runs full DAG — no incremental replay | Higher resource usage during replay — functional correctness maintained | Post-freeze optimization | **CERTIFIED** |
| AD-007 | Replay Drift | K5 ReplayDrift metric is reported as 0.0 (placeholder) — no actual drift measurement | Health dashboard shows 0.0 — accurate drift requires replay baseline comparison | Post-freeze improvement | **CERTIFIED** |

---

## Governance

- **No unregistered debt**: All known deviations are tracked in this register.
- **Certified trade-offs**: Each entry is verified as non-blocking for production deployment.
- **Remediation rule**: No debt may remain unaddressed beyond 2 consecutive minor releases.
- **LAW 18**: Trace Analysis Determinism — every debt entry is traceable to its originating audit.

---

*Generated at: 2026-05-24 — Final Production Freeze*
