# Phase 4: Runtime Intelligence, Composition Root, Service Contracts, Isolation & Control Plane

## Overview

Phase 4 transforms the system from a single-threaded execution library into a self-observing, self-enforcing, controlled runtime operating system with full isolation, service contracts, and meta-governance.

## Sections

- [3.8 — Runtime Trace Intelligence](#38--runtime-trace-intelligence)
- [3.9 — Composition Root Finalization](#39--composition-root-finalization)
- [D8 — Service Architecture & Runtime Contracts](#d8--service-architecture--runtime-contracts)
- [4 — Runtime Isolation Layer](#4--runtime-isolation-layer)
- [GAP 1 — Service Mesh](#gap-1--service-mesh)
- [GAP 2 — Control Plane](#gap-2--control-plane)
- [GAP 3 — Runtime OS](#gap-3--runtime-os)
- [GAP 4 — Suggestion-based Evolution](#gap-4--suggestion-based-evolution)
- [LAW 28-30 — Evolution Meta-Governance](#law-28-30--evolution-meta-governance)
- [Phase 5 — Distributed Runtime](#phase-5--distributed-runtime)
- [Test Statistics](#test-statistics)

---

## 3.8 — Runtime Trace Intelligence

**Files:** `core/codegraph/runtime_intelligence/`, `core/runtime_intelligence.py`

**What was built:**
- **HotspotAnalyzer**: Detects frequently executed execution paths in `core/codegraph/runtime_intelligence/hotspot_analyzer.py`
- **ExecutionTopology**: Maps execution flow as graph transformations in `core/codegraph/runtime_intelligence/execution_topology.py`
- **FailureTopology**: Maps failure clusters and propagation paths in `core/codegraph/runtime_intelligence/failure_topology.py`
- **RuntimeCentrality**: Measures node importance based on runtime data in `core/codegraph/runtime_intelligence/runtime_centrality.py`
- **ExecutionFrequencyTracker**: Tracks how often each node is executed in `core/codegraph/runtime_intelligence/execution_frequency_tracker.py`
- **RuntimeGraphBuilder**: Merges runtime execution data into the static CodeGraph in `core/codegraph/runtime_intelligence/runtime_graph_builder.py`
- **RuntimeDriftDetector**: Detects divergence between static architecture and runtime behavior in `core/codegraph/runtime_intelligence/runtime_drift_detector.py`
- **DriftClassifier**: Classifies drifts as addition, removal, frequency, or structural in `core/codegraph/runtime_intelligence/drift_classifier.py`
- **RuntimeIntelligence API**: `core/runtime_intelligence.py` — explain_execution, explain_failure, explain_dependency, why_executed
- **Canon LAW 17-19**: Added to `core/canon/rules.py`, `core/canon/context.py`, `core/canon/default_rules.py`

**Key insight:** Runtime behavior is now observable as graph transformations (LAW 17), continuously reconciled with static architecture (LAW 18), and all execution traces are explainable (LAW 19).

**Tests:** 45 tests in `tests/test_runtime_intelligence.py`

---

## 3.9 — Composition Root Finalization

**Files:** `core/runtime/bootstrap.py`, `core/composition/root.py`

**What was built:**
- **EmoRuntime**: Single entry point with lifecycle management (build → start → shutdown) in `core/runtime/bootstrap.py`
- **Context manager** support: `with EmoRuntime(config={...}) as runtime:`
- **Boot contract validation**: Validates tool_registry, optimizer, contract_validator at build time
- **Runtime intelligence wiring**: `runtime.intelligence` property exposes RuntimeIntelligence
- **Runtime OS wiring**: `runtime.os` property exposes RuntimeOS (added in GAP 3)
- **DI enforcement**: `root.build_execution_engine()` is the ONLY valid way to create an engine — direct import of `ExecutionEngine` banned

**Key insight:** Production code must ONLY use `EmoRuntime`. Direct use of `CompositionRoot` or `ExecutionEngine` is prohibited (enforced by AST scan test).

**Tests:** 18 tests in `tests/test_bootstrap.py`

---

## D8 — Service Architecture & Runtime Contracts

**Files:** `core/interfaces/scheduler.py`, `state_store.py`, `dispatcher.py`, `retry.py`, `lease.py`, `failure_propagation.py`

**What was built:**
- **IExecutionScheduler** — owns execution ordering (`order_levels`, `select_ready_nodes`, `allocate_worker`, `estimate_execution_order`)
- **IExecutionStateStore** — owns persistence and traces (`get/set_state`, `store_trace`, `save/restore_checkpoint`)
- **IExecutionDispatcher** — owns execution routing (`resolve_tool`, `can_dispatch`, `dispatch_local/remote`, `validate_contract/output`)
- **IExecutionRetryHandler** — owns retry semantics (`classify_failure`, `should_retry`, `compute_backoff`, `handle_exhaustion`, `record_attempt`)
- **IExecutionLeaseManager** — owns lease lifecycle (`acquire`, `release`, `heartbeat`, `is_expired`, `owner`, `release_all`)
- **FailurePropagationPolicy** — FailureDomain, PropagationAction, DegradeMode, PROPAGATION_MATRIX (3 domains × 11 rules)
- **Canon LAW 20-27**: Failure propagation (LAW 20-22) + Service ownership (LAW 23-27)

**Key insight:** Each Protocol owns exactly one domain. No service exposes methods from another service's domain. Cross-service failure propagation is explicitly defined as a matrix in code.

**Tests:** 21 tests in `tests/test_service_isolation.py`

---

## 4 — Runtime Isolation Layer

**Files:** `core/runtime/sandbox/`, `core/security/capabilities/`, `core/runtime/io/`, `core/runtime/resources/`, `core/runtime/isolation/`

**What was built:**

### 4.1 — Execution Sandbox
- **SandboxExecutor**: Subprocess worker with timeout + RLIMIT_AS/RLIMIT_CPU in `core/runtime/sandbox/sandbox_executor.py`
- **SandboxContext**: Configured with CPU/memory/FS/network limits in `core/runtime/sandbox/sandbox_context.py`
- **SandboxManager**: Create/destroy lifecycle in `core/runtime/sandbox/sandbox_manager.py`
- **SandboxErrors**: SandboxViolationError, ResourceLimitExceeded, ExecutionTimeoutError in `core/runtime/sandbox/sandbox_errors.py`

### 4.2 — Capability Security
- **Capability**: null/full/restricted factories in `core/security/capabilities/capability_model.py`
- **CapabilityRegistry**: Tool→capability mapping + auto-load from specs in `core/security/capabilities/capability_registry.py`
- **CapabilityGuard**: Pre-execution validation — NO capability → NO execution in `core/security/capabilities/capability_guard.py`

### 4.3 — IO & Network Isolation
- **IOPolicyEngine**: allow/deny + domain/size filtering in `core/runtime/io/io_policy_engine.py`
- **NetworkIsolation**: Outbound interceptor + DNS/URL filter + private address blocking in `core/runtime/io/network_isolation.py`
- **FilesystemIsolation**: Path whitelist + read/write + extension filter + symlink blocking in `core/runtime/io/filesystem_isolation.py`

### 4.4 — Resource Governance
- **ResourceTracker**: CPU/memory/IO per execution in `core/runtime/resources/resource_tracker.py`
- **QuotaManager**: Per-execution/worker/global quotas with QuotaExceeded in `core/runtime/resources/quota_manager.py`
- **ResourceEnforcer**: Pre-check + mid-flight kill in `core/runtime/resources/resource_enforcer.py`

### 4.5 — Isolation Runtime Bridge
- **IsolationRuntime**: Wraps all layers into single 5-step execute() in `core/runtime/isolation/isolation_runtime.py`

**Key insight:** Phase 4 shifts from "trusted in-process execution" to "untrusted isolated execution with enforced boundaries." Three enforcement layers: capability (what you can do), IO (where you can go), resources (how much you can use).

**Tests:** 81 tests in `tests/test_runtime_isolation.py`

---

## GAP 1 — Service Mesh

**Files:** `core/runtime/mesh/`

**What was built:**
- **MeshProtocol**: Internal RPC with MeshEnvelope, MeshMessageType (REQUEST/RESPONSE/ERROR)
- **ServiceRegistry**: register/heartbeat/discover/prune with TTL, capability-based discovery
- **ServiceMesh**: Local handler registration + sync/async call + routing
- **FailurePropagator**: Callback-based failure propagation with history + instance status tracking

**Key constraint:** Logical in-process mesh, NOT K8s-style networking (per user requirement).

**Tests:** 20 tests in `tests/test_gaps_1_4.py` (TestMeshProtocol, TestServiceRegistry, TestServiceMesh, TestFailurePropagator)

---

## GAP 2 — Control Plane

**Files:** `core/runtime/control/`

**What was built:**
- **SystemState**: Global state container with phase (BOOTING/ACTIVE/DEGRADED/SHUTDOWN), counters, uptime
- **Reconciler**: Desired state diff — detects scale-up/down, pending task overflow
- **WorkerOrchestrator**: Worker lifecycle — create/terminate/scale/assign/complete + active count
- **HealthMonitor**: Heartbeat-based health checks with TTL + degradation alerts
- **ControlPlane**: Decision engine with ControlAction, start/shutdown lifecycle, reconciler tick

**Key constraint:** Light orchestration, NOT cluster manager (per user requirement).

**Tests:** 22 tests in `tests/test_gaps_1_4.py` (TestSystemState, TestReconciler, TestWorkerOrchestrator, TestHealthMonitor, TestControlPlane)

---

## GAP 3 — Runtime OS

**Files:** `core/runtime/os/runtime_os.py`

**What was built:**
- **RuntimeOS**: Unified external API surface with:
  - `submit(dag)` → execution_id
  - `observe(id)` → execution status + events + timing
  - `replay(id)` → new execution_id (deep clone DAG)
  - `cancel(id)` → bool
  - `scale(n)` → worker count
  - `list_executions(status, limit)` → filtered list
  - `status_summary()` → system overview
- Wired into EmoRuntime as `runtime.os` property
- Integrated with ControlPlane, WorkerOrchestrator, ServiceMesh

**Key insight:** This is the ONLY interface external consumers should use. Everything is accessible through these 5 operations: submit, observe, replay, cancel, scale.

**Tests:** 12 tests in `tests/test_gaps_1_4.py` (TestRuntimeOS)

---

## GAP 4 — Suggestion-based Evolution

**Files:** `core/runtime/evolution/`

**What was built:**
- **RuleRefiner**: Analyzes runtime execution data (failures, blocks, hotspots) and produces RefinementSuggestion objects
- **CanonEvolver**: Filters suggestions by confidence threshold (conservative/balanced/verbose), packages into EvolutionReport
- **FeedbackActuator**: Generates FeedbackReport with runtime snapshot, fires callbacks, records audit

**Key constraint:** Suggestion-only, NO auto-mutation. System proposes, human decides (per user requirement).

**Tests:** 18 tests in `tests/test_gaps_1_4.py` (TestRuleRefiner, TestCanonEvolver, TestFeedbackActuator)

---

## LAW 28-30 — Evolution Meta-Governance

**Files:** `core/canon/rules.py`, `core/canon/context.py`, `core/canon/default_rules.py`, `core/runtime/evolution/canon_evolver.py`

**What was built:**

| Law | Severity | Meaning | Implementation |
|---|---|---|---|
| **LAW 28** | CRITICAL | Human-in-the-loop Evolution Gate | `CanonEvolver(approval_func=...)` — no evolution without explicit approval |
| **LAW 29** | HIGH | Immutable Audit Trail | `CanonEvolver(audit_log=...)` — every evolution is logged with ID, timestamp, suggestions |
| **LAW 30** | HIGH | Safe Rollback | `CanonEvolver(rollback_func=...)` — `evolver.rollback(token)` reverses evolution |

**Key insight:** Before LAW 28-30, the system could learn + adapt. After LAW 28-30, the system can learn + adapt + BUT controlled. This is the Meta-Governance Layer: control over evolution itself.

The Canon now has **17 laws** (LAW 14-30):
- LAW 14-16: CRITICAL — Structure enforcement
- LAW 17-18: HIGH — Runtime observability
- LAW 19: MEDIUM — Execution explainability
- LAW 20-22: HIGH — Failure propagation
- LAW 23-27: HIGH — Service ownership
- LAW 28: CRITICAL — Evolution gate
- LAW 29-30: HIGH — Audit & rollback

**Tests:** 16 tests (6 in `test_canon_validator.py`, 10 in `test_gaps_1_4.py`)

---

## Test Statistics

| Phase | Tests | File |
|---|---|---|
| 3.8 — Runtime Intelligence | 45 | `tests/test_runtime_intelligence.py` |
| 3.9 — Bootstrap | 18 | `tests/test_bootstrap.py` |
| D8 — Service Isolation | 21 | `tests/test_service_isolation.py` |
| 4 — Runtime Isolation | 81 | `tests/test_runtime_isolation.py` |
| GAP 1-4 | 73 | `tests/test_gaps_1_4.py` |
| Canon laws | 19+ | `tests/test_canon_validator.py` |
| **Total new** | **257+** | |
| **Full suite** | **997 pass, 5 pre-existing fail** | `tests/` |

## CodeGraph

- **2,604 nodes**, **2,450 edges**
- Average risk: **0.026**, max risk: **1.0**
- **24 nodes** above 0.8 threshold (active architectural debt)
- New baseline: `3.9.0-d8`
- Known violations tracked in `artifacts/codeguard/known-violations.json`

## Closed Loops

| Loop | Path | Purpose |
|---|---|---|
| **1 (static)** | emo-guard → CodeGraph → DriftDetector → CanonValidator | Pre-commit architecture enforcement |
| **2 (runtime)** | ExecutionEngine → IEventBus → EventStore → CodeGraphEventSubscriber → RuntimeStats | Runtime observability |
| **3 (self-awareness)** | RuntimeIntelligence ← EventStore + RuntimeStats + CodeGraph | explain_execution/failure/dependency |
| **4 (mesh)** | ServiceMesh ← ServiceRegistry + MeshProtocol + FailurePropagator | Internal routing + failure notification |
| **5 (control)** | ControlPlane ← SystemState + Reconciler + HealthMonitor + WorkerOrchestrator | Reconciliation + scaling + health |
| **6 (evolution)** | FeedbackActuator ← RuleRefiner + CanonEvolver | Suggestions → human approval → architecture change |

## Architecture Summary

```
                     ┌─────────────────┐
                     │   EmoRuntime     │  ← Single entry point
                     │  (bootstrap.py)  │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
      ┌──────────────┐ ┌──────────┐ ┌──────────────┐
      │ Composition  │ │ RuntimeOS│ │ RuntimeIntel │
      │    Root      │ │ (GAP 3)  │ │   (3.8)      │
      └──────┬───────┘ └────┬─────┘ └──────────────┘
             │              │
    ┌────────┼────────┐     │
    ▼        ▼        ▼     │
┌────────┐┌────────┐┌────┐  │
│Engine  ││Canon   ││Svc │  │
│(Core + ││Validator││I/F│  │
│Runtime)││(LAWs)  ││(D8)│  │
└────────┘└────────┘└────┘  │
                             │
    ┌────────────────────────┘
    ▼
┌─────────────────────────────────────┐
│         IsolationRuntime (4.5)       │
├───────────────────┬─────────────────┤
│ CapabilityGuard   │  IOPolicyEngine │
│ (4.2)             │  (4.3)          │
├───────────────────┼─────────────────┤
│ ResourceEnforcer  │  SandboxManager │
│ (4.4)             │  (4.1)          │
└───────────────────┴─────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│           Control Plane (GAP 2)     │
├──────────┬──────────┬──────────────┤
│ System   │Reconciler│   Health     │
│ State    │          │   Monitor    │
├──────────┴──────────┴──────────────┤
│        Worker Orchestrator         │
└────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│          Service Mesh (GAP 1)       │
├──────────┬──────────┬──────────────┤
│ Service  │   Mesh   │   Failure    │
│ Registry │ Protocol │  Propagator  │
└──────────┴──────────┴──────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│        Evolution Loop (GAP 4)       │
├──────────┬──────────┬──────────────┤
│ Rule     │  Canon   │  Feedback    │
│ Refiner  │ Evolver  │  Actuator    │
│          │(LAW 28-30)│              │
└──────────┴──────────┴──────────────┘
```

---

---

## Phase 5 — Distributed Runtime

**Files:** `core/runtime/mesh/remote/`

**What was built:**

### Remote Serialization
- **`serialization.py`**: MeshEnvelope ←→ dict ←→ JSON — `envelope_to_dict`, `dict_to_envelope`, `envelope_to_json`, `json_to_envelope`

### HTTP Transport
- **`transport.py`**:
  - `RemoteTransportClient`: httpx-based HTTP client for sending MeshEnvelopes to remote nodes (`send_request`, `send_heartbeat`, `register_remote`)
  - `RemoteTransportServer`: Threaded HTTP server using `ThreadingHTTPServer` + `BaseHTTPRequestHandler` — accepts POST to `/mesh/call`, `/mesh/heartbeat`, `/mesh/register`
  - `RemoteTransportError`: Exception for transport failures

### Distributed Registry
- **`discovery.py`**:
  - `PeerNode`: Represents a known peer (node_id, host, port, last_seen, status)
  - `DistributedRegistry`: Combines local ServiceRegistry + peer discovery — supports `register_peer`, `remove_peer`, `discover_remote`, `sync_peers` (gossip protocol), `check_peer_health`, `announce`

### MeshNode
- **`node.py`**: Full mesh node combining local ServiceMesh + HTTP server + HTTP client + DistributedRegistry
  - `register_handler(service, method, handler)` — local handler registration
  - `add_peer(node_id, host, port)` — add remote peer
  - `start()` / `shutdown()` — lifecycle
  - `announce_to_peers()` — announce services to all peers
  - `call_remote(service, method, payload, peer_id)` — call a remote peer's service
  - `discover_remote(service)` — discover services across all peers

### Architecture

```
┌─────────────────────────────────────────────┐
│               MeshNode A                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │  Service  │  │  Remote  │  │Distributed│  │
│  │   Mesh    │  │ Transport│  │ Registry  │  │
│  │  (local)  │  │  Server  │  │           │  │
│  └─────┬─────┘  └────┬─────┘  └─────┬─────┘  │
│        │             │              │         │
└────────┼─────────────┼──────────────┼─────────┘
         │             │              │
         │    HTTP POST /mesh/call    │
         │    ───────────────►        │
         │             │              │
┌────────┼─────────────┼──────────────┼─────────┐
│  MeshNode B          │              │         │
│  ┌─────▼─────┐  ┌───▼──────┐  ┌───▼───────┐  │
│  │  Service  │  │  Remote  │  │Distributed│  │
│  │   Mesh    │  │ Transport│  │ Registry  │  │
│  │  (local)  │  │  Server  │  │           │  │
│  └───────────┘  └──────────┘  └───────────┘  │
└─────────────────────────────────────────────┘
```

**Key insight:** Phase 5 transforms the logical in-process mesh into an actual network mesh. Nodes communicate over HTTP, share registry state via gossip protocol, and can dispatch execution to remote nodes.

**Tests:** 32 tests in `tests/test_phase5_distributed.py`

---

## CodeGraph & Drift Baseline

| Metric | Value |
|--------|-------|
| CodeGraph nodes | 1,630 |
| CodeGraph edges | 1,647 |
| Average risk | 0.3423 |
| Max risk | 1.0 |
| High-risk nodes (>0.8) | 6 |
| Baseline version | `4.0.0-gaps` |
| Baseline file | `artifacts/codegraph/drift/4.0.0-gaps.json` |

## Test Statistics

| Phase | Tests | File |
|---|---|---|
| 3.8 — Runtime Intelligence | 45 | `tests/test_runtime_intelligence.py` |
| 3.9 — Bootstrap | 18 | `tests/test_bootstrap.py` |
| D8 — Service Isolation | 21 | `tests/test_service_isolation.py` |
| 4 — Runtime Isolation | 81 | `tests/test_runtime_isolation.py` |
| GAP 1-4 | 73 | `tests/test_gaps_1_4.py` |
| Canon laws | 19+ | `tests/test_canon_validator.py` |
| Phase 5 — Distributed Runtime | 32 | `tests/test_phase5_distributed.py` |
| **Total new** | **289+** | |
| **Full suite** | **1,029 pass, 5 pre-existing fail** | `tests/` |

*Document generated: 2026-05-20 — 1,029 tests passing, 5 pre-existing failures*

