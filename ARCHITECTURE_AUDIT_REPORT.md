# Architecture Audit Report

**Date:** 2026-05-19  
**Auditor:** Independent Architecture Audit (Phase 5→14)  
**Method:** Evidence-based — file inspection, import tracing, test execution, E2E pipeline run

---

## A) Real Completion Percentage

Each metric is based on actual code analysis, not test pass rates or summaries.

| Layer | Est. Complete | Basis |
|-------|:------------:|-------|
| **Core Architecture** (Phases 1-4) | 90% | All scaffolding exists. Missing: HTTP endpoint exposure for GraphQuery/AIContextEngine, user documentation |
| **Parser Layer** (Phase 5) | 95% | 722 lines, 5 classes, 23 methods. Python/JS/TS/fallback parsers all working. 3 unused imports in repository_indexer. The `vararg` key in parser key mapping references outdated Python AST structures |
| **Repository Indexer** (Phase 5) | 90% | 1022 lines, full incremental scanning, retry, dead-letter. Potential connection leak in `_update_file_record`. No embedding-index sync check |
| **Graph Query** (Phase 5) | 95% | 533 lines, read-only. BFS traversal, impact analysis, name→ID resolution. No WAL mode on connections. |
| **AI Context Engine** (Phase 5) | 90% | 396 lines. Pure read-only. build_llm_context produces well-structured output. Missing: direct test coverage |
| **Static Analysis** (Phase 6) | 95% | 404 lines. Pure AST-only, deterministic. 9 role classifications + behavior/complexity. Verified working in E2E test |
| **AI Agent** (Phase 7) | 85% | 471 lines, 12 methods. All 5 query types (explain/impact/hotspots/why/refactor) implemented. No tests specific to this module |
| **Graph Retrieval** (Phase 8) | 90% | 478 lines, 3 classes. HeuristicRanker, SmartFilter, GraphRetrievalEngine. N+1 pattern: `heuristic_analysis` called once per symbol in `ranked_hotspots` |
| **Orchestrator** (Phase 9) | 85% | 660 lines, 6 classes. QueryPlanner regex handles 17 intent patterns. No Planner → AI Agent feedback loop for failed intents |
| **Semantic RAG** (Phase 10) | 90% | EmbeddingEngine 181 lines, SemanticStore 232 lines, HybridRetriever 619 lines. FAISS + sentence-transformers working in E2E test. No embedding cache |
| **Self-Tuning** (Phase 11) | 85% | AdaptiveWeightEngine 419 lines, FeedbackLoop 194 lines, QueryReplay 319 lines. Boost logic works. Missing: decay-aware success_rate in practice |
| **Guardrails** (Phase 12) | 90% | 580 lines, 10 classes, 32 methods. All 6 subsystems implemented and tested. RollbackManager only in-memory — no persistence |
| **Telemetry** (Phase 13) | 85% | MetricsStore 563 lines, Timeline 232 lines, QueryAnalytics 412 lines. Full event-sourced architecture. Analytics reads from store but QueryReplay feeds are separate |
| **Execution Memory** (Phase 14) | 90% | 859 lines, 6 classes, 54 methods. 5 SQLite tables, session lifecycle, reasoning traces, plan versioning. Auto-incrementing plan_number |
| **Execution Engine** (Phase 15) | 85% | 654 lines, 12 classes, 32 methods. DAG + 8-state machine + retry + rollback + FailureIntelligence. Missing: timeout enforcement in _run_with_timeout (no actual threading timeout) |
| **Security / AI Isolation** | 90% | WORKSPACE_ROOT, _safe_path, JWT auth middleware all present |
| **Production Readiness** | 35% | No rate limiting, no connection pooling, no health check endpoints for sub-systems, all data in local SQLite with no backup/export, no deployment config |

---

## B) Architecture Dependency Map (Real)

```
parsers.py ─────────────────────────────→ static_analyzer.py
    ↓
repository_indexer.py ────→ db_writer.py (SQLite writes)
    ↓
graph_query.py (read-only SQLite)
    ↓
ai_context_engine.py (read-only over graph_query)
    ↓
graph_retrieval.py ───────→ graph_query + ai_context_engine
    ↓
ai_agent.py ──────────────→ graph_query + ai_context_engine + graph_retrieval
    ↓
orchestrator.py ──────────→ graph_retrieval + ai_agent + ai_context_engine + graph_query + hybrid_retriever
    ↓
hybrid_retriever.py ──────→ graph_retrieval + semantic_store + embedding_engine + adaptive_weights + query_replay + metrics_store
    ↓
embedding_engine.py (standalone)
semantic_store.py (standalone, FAISS)
    ↓
adaptive_weights.py ──────→ feedback_loop + guardrails + metrics_store
    ↑
query_replay.py (standalone, SQLite)
    ↓
feedback_loop.py (standalone)
    ↓
guardrails.py (standalone, 6 components)
    ↓
metrics_store.py (standalone, 4 SQLite tables)
    ↓
timeline.py ──────────────→ metrics_store
query_analytics.py ────────→ metrics_store + query_replay
    ↓
execution_memory.py (standalone, 5 SQLite tables)
execution_engine.py (standalone, DAG + state machine)
```

### Key dependency findings:

1. **No circular imports detected** — the DAG is acyclic in both direct and transitive directions.

2. **Standalone modules** (no core/ imports): `embedding_engine`, `semantic_store`, `feedback_loop`, `guardrails`, `query_replay`, `metrics_store`, `execution_memory`, `execution_engine`, `static_analyzer`, `graph_query`. These are well-factored.

3. **Highest inbound coupling**: `metrics_store` (imported by 4 files), `graph_query` (4 files).

4. **Highest outbound coupling**: `hybrid_retriever.py` (imports from 5 other core modules), `adaptive_weights.py` (imports from 3 modules).

---

## C) Most Dangerous Issues (Ranked)

### Critical

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | **`_run_with_timeout` does NOT enforce timeout** | `execution_engine.py:570` | The method runs the tool function synchronously without any threading/signaling timeout. A long-running tool blocks the entire engine indefinitely. |
| 2 | **GraphQuery connections lack WAL mode** | `graph_query.py` | In high-concurrency scenarios (parallel queries from orchestrator), this can lead to `database is locked` errors. Repository indexer uses WAL but query layer does not. |
| 3 | **No embedding cache in HybridRetriever** | `hybrid_retriever.py` | Every `retrieve()` call re-embeds the same query text. With sentence-transformers this is ~100ms/call. For repeated queries (e.g. `replay.find_similar`), this wastes significant time. |
| 4 | **N+1 query pattern in ranked_hotspots** | `graph_retrieval.py` | `ranked_hotspots()` loops through each hotspot and calls `heuristic_analysis()` individually, which runs a separate `traverse_depth()` per symbol. O(n) DB round-trips for n symbols. |

### High

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 5 | **Potential connection leak in `_update_file_record`** | `repository_indexer.py:382` | The method opens a raw sqlite3 connection outside the DBWorker queue. If the UPDATE fails and falls through to INSERT, the connection is not guaranteed closed in all error paths. |
| 6 | **DEVELOPER.md is completely outdated** | `DEVELOPER.md` | Describes v4.0.0 stub state. Claims brain.py/agent.py/memory.py/tools.py are stubs (they're not). Claims 16 API endpoints are missing (they exist). Every Phase 5-15 is undocumented. New developers would be actively misled. |
| 7 | **`execution_memory.py`: 54 methods — God-class risk** | `execution_memory.py` | At 859 lines and 54 methods, `ExecutionMemory` violates Single Responsibility. It handles sessions, events, reasoning, tasks, and plans in one class with inline SQL. |
| 8 | **`execution_engine.py`: DAGBuilder unused anywhere** | `execution_engine.py:610-654` | The `DAGBuilder` fluent API is dead code — never imported or instantiated outside tests. |

### Medium

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 9 | **Guardrails RollbackManager has no persistence** | `guardrails.py` | Rollback state is purely in-memory. If the process restarts, all rollback history and the rolled_back flag are lost. |
| 10 | **QueryAnalytics imports `EVENT_QUERY_EXECUTED` but never uses it** | `query_analytics.py` | Unused import. Minor but indicates a disconnect in development. |
| 11 | **`feedback_loop._recent_feedback` has unbounded growth** | `feedback_loop.py` | The deque has `maxlen=None` by default — in long-running systems with heavy feedback, memory grows without bound. |
| 12 | **Orchestrator has no Planner failure feedback** | `orchestrator.py` | If `QueryPlanner` fails to classify an intent, the error propagates to the user with no retry or fallback strategy. |
| 13 | **tests/test_async_task_manager.py has 0 tests** | `tests/test_async_task_manager.py` | File contains 4 asserts but no `def test_` functions — it's a usage script, not a test suite. |

### Low

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 14 | **`parsers.py`: vararg/kwarg key references outdated AST** | `parsers.py:85-91` | Python 3.8+ uses `arg.keyword` not separate vararg/kwarg. The mapping exists but may not produce correct results for `def f(*args, **kwargs)`. |
| 15 | **`timeline.py` relies on `MetricsStore` private `_safe_json` — duplicated across files** | `timeline.py`, `execution_memory.py` | Both files implement `_safe_json()` identically. Code duplication. |
| 16 | **No monitoring/health endpoint for system sub-components** | `main.py` | No endpoint to check if semantic index is loaded, graph DB is accessible, or embedding model is available. |

---

## D) What Will Break Later

| Scenario | Risk | Why |
|----------|:----:|-----|
| **Concurrent users >5** | 🔴 High | SQLite WAL mode helps but graph_query.py doesn't use it. Repository indexer's single-writer queue becomes a bottleneck. All telemetry (metrics, replay, execution memory) uses separate SQLite databases — 5 concurrent open DBs per request. |
| **Repository >50K files** | 🔴 High | Graph traversal uses in-memory BFS with no pagination. `top_symbols` does a full `SUM(call_count)` with GROUP BY. HeuristicRanker iterates all symbols. |
| **Long-running tool execution** | 🔴 High | `execution_engine.py:_run_with_timeout` is not actually a timeout — it calls the runner synchronously. A tool that hangs for 60s blocks the entire engine. |
| **Process restart** | 🟡 Medium | Rollback state lost. Learning state (boost rates) lost — only persisted in RankingFeedbackLoop (in-memory). MetricsStore survives (SQLite) but the weight adaptations don't. |
| **Semantic index desync** | 🟡 Medium | No mechanism to detect when the graph DB has more symbols than the FAISS index. They can drift apart. FAISS index saved on explicit `save()` only. |
| **Memory pressure** | 🟡 Medium | `feedback_loop._recent_feedback` is unbounded. `execution_engine.FailureIntelligence._stats` is unbounded. In sustained operation, these grow without limit. |
| **Schema migration** | 🟡 Medium | No migration system for any of the 5+ SQLite databases. Schema changes require manual intervention. |

---

## E) Production Readiness Assessment

### What works today
- Parsing Python/JS/TS repos
- Building and querying a dependency graph
- Hybrid (graph+semantic) retrieval with dynamic weighting
- Self-tuning weight adjustment via feedback
- 6 guardrails subsystems (drift, boundaries, decay, regression, shadow, rollback)
- Full telemetry pipeline (events, timeline, analytics)
- Session-based execution memory
- DAG-based execution engine with retry/rollback

### What's missing for production

| Requirement | Status | Notes |
|-------------|--------|-------|
| Connection pooling | ❌ | Every SQLite module opens/closes connections per call |
| Rate limiting | ❌ | No protection against DoS or abusive clients |
| Health checks | ❌ | No `/health` endpoint for sub-system status |
| Metrics dashboard | ❌ | Telemetry is stored but no live visualization |
| Backup/export | ❌ | No mechanism to back up any of the 5+ SQLite DBs |
| Monitoring alerts | ❌ | Guardrails detect problems but no alert routing (email, webhook) |
| Schema migrations | ❌ | Alembic-style migrations for all databases |
| Authentication for AI endpoints | ❌ | Orchestrator/GraphQuery exposed via imports but no API auth |
| Performance benchmarks | ❌ | No baseline for latency, throughput, or memory |
| Error budgeting | ❌ | No mechanism to measure or enforce SLOs |
| Graceful degradation | ⚠️ Partial | HybridRetriever has `_fallback_graph()` but other layers don't |

---

## F) Is This an "Advanced AI Code Intelligence System"?

**Verdict: Yes — with significant caveats.**

### What makes it genuinely advanced:

1. **Architecture completeness**: 15 phases implemented across 20 core files (10,834 total lines). The design follows a clear layering: parse → index → graph → retrieve → reason → orchestrate → learn → guard → telemetry → remember → execute.

2. **Real graph-first retrieval**: Not a simple keyword search. Uses actual dependency graph (callers/callees relationships) with BFS traversal, cycle safety, and impact analysis. Combined with FAISS semantic search via configurable weighting.

3. **Self-tuning feedback loop**: AdaptationRate tracking with 6 feedback signals, dynamic weight boosting per strategy profile, and guardrails that detect strategy collapse and performance regression.

4. **Event-sourced telemetry**: Proper event-sourced MetricsStore with fixed taxonomy. Not ad-hoc logging but structured events designed for replay, debugging, and explainability.

5. **DAG execution engine**: Proper 8-state machine with topological ordering, retry with exponential backoff, rollback of transitive successors, and failure intelligence.

### What makes it still a prototype:

1. **Documentation is entirely outdated**: The only developer-facing documentation describes v4.0.0 stubs. A new developer would be completely misled.

2. **No HTTP exposure**: The AI pipeline (orchestrator, hybrid retrieval, adaptive engine) exists only as importable classes — not accessible via API endpoints.

3. **Fragile SQLite architecture**: 5+ separate SQLite databases with no connection pooling, no migration system, no backup strategy. Most connections don't use WAL mode.

4. **No production hardening**: No rate limiting, no health checks, no monitoring alerts, no graceful degradation beyond the hybrid fallback. The ExecutionEngine's "timeout" doesn't actually enforce timeouts.

5. **Critical gaps in memory safety**: Several unbounded data structures, no embedding cache, N+1 queries in the hot path.

**Final Assessment:**
- **Architecture quality**: 7/10 — Well-designed layers with clear separation, but too many standalone SQLite databases and no circular-import safety net.
- **Implementation quality**: 6/10 — Code is real and functional, but has notable quality issues (dead code, connection leaks, fake timeout, unbounded growth).
- **Production readiness**: 2/10 — Would require significant investment in hardening, monitoring, and deployment infrastructure before production use.
- **Documentation**: 2/10 — DEVELOPER.md is actively harmful; README.md is incomplete; ARCHITECTURE_DESIGN.md is closest to accurate but still lacks 2 tables and 3 directories.

---

## Appendix: Real File & Test Summary

### Core files (20/20 exist, all ≥181 lines)

| File | Lines | Classes | Methods |
|------|-------|---------|---------|
| repository_indexer.py | 1022 | 1 | 18 |
| execution_memory.py | 859 | 6 | 54 |
| parsers.py | 722 | 5 | 23 |
| orchestrator.py | 660 | 6 | 15 |
| execution_engine.py | 654 | 12 | 32 |
| hybrid_retriever.py | 619 | 3 | 16 |
| guardrails.py | 580 | 10 | 32 |
| metrics_store.py | 563 | 1 | 31 |
| graph_query.py | 533 | 1 | 15 |
| graph_retrieval.py | 478 | 3 | 22 |
| ai_agent.py | 471 | 1 | 12 |
| adaptive_weights.py | 419 | 1 | 15 |
| query_analytics.py | 412 | 4 | 10 |
| static_analyzer.py | 404 | 1 | 9 |
| ai_context_engine.py | 396 | 1 | 5 |
| query_replay.py | 319 | 2 | 17 |
| timeline.py | 232 | 1 | 5 |
| semantic_store.py | 232 | 1 | 12 |
| embedding_engine.py | 181 | 1 | 10 |
| feedback_loop.py | 194 | 2 | 11 |

### Test files (6 suites, 227 passing tests)

| File | Tests | Asserts | Covers |
|------|-------|---------|--------|
| test_phase11.py | 36 | 79 | QueryReplay, FeedbackLoop, AdaptiveWeightEngine, integration |
| test_phase12.py | 48 | 102 | All 6 guardrails components, integration |
| test_phase13.py | 38 | 89 | MetricsStore, Timeline, QueryAnalytics, integration |
| test_phase14.py | 33 | 110 | Full ExecutionMemory, sessions, plans, tasks |
| test_phase15.py | 44 | 96 | DAG, state machine, retry, rollback, FailureIntelligence |
| test_hybrid_retrieval.py | 28 | 48 | HybridRetriever, WeightsAdvisor, normalization |

**Total: 227 tests, 524 asserts, 0 failures across all suites.**

### Test quality assessment:
- ✅ Unit tests exist for all Phase 11-15 modules
- ✅ Integration tests chain multiple layers together
- ✅ Edge cases tested (empty states, not-found, insufficient samples)
- ❌ No tests for `parsers.py`, `static_analyzer.py`, `ai_context_engine.py`, `ai_agent.py`, `graph_query.py` in isolation
- ❌ `test_async_task_manager.py` has 0 actual tests
- ❌ No performance/benchmark tests
- ❌ All tests pass deterministically but use mocks extensively — no real DB integration in most tests
