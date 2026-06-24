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
| AD-003 | Multi-Agent | Agent lifecycle layer (G5) has zero test coverage — conceptual only | No runtime impact — layer is not activated in production | K6 phase | **RESOLVED** — 30 tests were written; `core/runtime/agents/` directory deleted in T-A3 (dead code consolidation) |
| AD-004 | Telemetry | F4 TelemetryAggregator skips DAG visualization data for DAGs > 500 nodes | Dashboard DAG view is sparse for large DAGs — CLI/API unaffected | K6 optimization phase | **RESOLVED** — `DAGVisualizer.graph_structure()` truncates at 500 nodes with truncated=True flag; total_node_count and edge_count reported |
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

## Completed in 2026-06-24 Session

| ID | Area | Debt Description | Resolution |
|----|------|------------------|-----------|
| AD-008 | Tracing duplication | `core/runtime/tracing/distributed_tracer.py` duplicated in `observability/distributed_tracer.py` | **MERGED** — observability version kept, tracing/ deleted, SpanStatus enum canonicalized across 4 files |
| AD-009 | Scheduler duplication | `core/scheduler/resource_scheduler.py` duplicated as `core/runtime/resource_scheduler/` | **MERGED** — runtime version kept, legacy API methods added, 10 properties restored, 3 tests fixed |
| AD-010 | Keychain test pollution | `KeychainProvider._cache` class-level attribute caused cross-test pollution; `.emo_settings.json` interfered with test isolation | **RESOLVED** — cache cleared in fixture, settings file mocked via monkeypatch, 8/8 tests pass |
| AD-011 | Stale doc references | 6 `cognitive/` path references in `EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md` pointed to deleted files | **UPDATED** — changed to `core/runtime/multi_agent/` |
| AD-012 | ERP connector dead import | `from enum import Enum` dangling at end of `erp_connector.py` | **REMOVED** — 72-line file cleaned |

*Generated at: 2026-06-24 — Post-Architecture-Audit Session*
