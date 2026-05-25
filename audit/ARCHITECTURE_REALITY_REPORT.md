# Architecture Reality Report

**Audit Date:**  2026-05-21 04:02:12.005654
**Role:** Hostile Verification Audit
**Assumption:** Nothing is real until proven.

## Executive Summary

- **Classes:** 200
- **Public Methods:** 1050
- **Critical Placeholders:** 5
- **Suspicious Placeholders:** 142
- **Pure Delegate Wrappers:** 55
- **Unused Modules:** 63
- **Assertionless Tests:** 41
- **Broken Execution Layers:** 0

## Critical Findings

### NotImplementedError (Runtime Critical)

- `core/parsers.py:165` — `raise NotImplementedError("Subclasses must implement parse()")`
- `core/parsers.py:478` — `raise NotImplementedError("Tree-sitter JS not yet implemented")`
- `core/parsers.py:590` — `raise NotImplementedError("Tree-sitter TS not yet implemented")`
- `core/service_registry.py:49` — `raise NotImplementedError`
- `core/worker_runtime.py:281` — `raise NotImplementedError(`

## Public API Inventory

**200** classes with **1050** public methods across the codebase.

### Top Subsystems by Method Count

- `core`: 1050 methods

### Contracts (Protocols / ABCs)

- `IExecutionDispatcher` in `core.interfaces.dispatcher`
- `IEventBus` in `core.interfaces.event_bus`
- `IDAGOptimizer` in `core.interfaces.execution`
- `IExecutionEngine` in `core.interfaces.execution_engine`
- `IContractValidator` in `core.interfaces.governance`
- `IComplianceValidator` in `core.interfaces.governance`
- `IExecutionLeaseManager` in `core.interfaces.lease`
- `IExecutionRetryHandler` in `core.interfaces.retry`
- `IExecutionScheduler` in `core.interfaces.scheduler`
- `IExecutionStateStore` in `core.interfaces.state_store`
- `ICostTracker` in `core.interfaces.systems`
- `IDAGSizeLimiter` in `core.interfaces.systems`
- `ICheckpointManager` in `core.interfaces.systems`

### ToolSpecs


### Scheduler Components

- `CostAwareScheduler` in `core.cost_intel` (1 methods)
- `DistributedScheduler` in `core.distributed_scheduler` (3 methods)
- `IExecutionScheduler` in `core.interfaces.scheduler` (4 methods)
- `ResourceRequirements` in `core.scheduler.resource_scheduler` (1 methods)
- `WorkerResource` in `core.scheduler.resource_scheduler` (9 methods)
- `UserQuota` in `core.scheduler.resource_scheduler` (3 methods)
- `FairnessModel` in `core.scheduler.resource_scheduler` (4 methods)
- `PriorityQueue` in `core.scheduler.resource_scheduler` (3 methods)
- `PriorityScheduler` in `core.scheduler.resource_scheduler` (3 methods)
- `ResourceScheduler` in `core.scheduler.resource_scheduler` (13 methods)

### Replay APIs

- `DAGReplayEngine` in `core.dag_replay` (5 methods)
- `DistributedReplayEngine` in `core.distributed_replay` (6 methods)
- `QueryReplay` in `core.query_replay` (8 methods)
- `ReplayEngine` in `core.replay.engine` (4 methods)
- `QueryReplayEngine` in `core.replay.engine` (7 methods)

### Distributed/Mesh APIs

- `DistributedCheckpointManager` in `core.distributed_checkpoint` (6 methods)
- `DistributedRecoveryManager` in `core.distributed_checkpoint` (4 methods)
- `DistributedReplayEngine` in `core.distributed_replay` (6 methods)
- `DistributedScheduler` in `core.distributed_scheduler` (3 methods)
- `WorkerNode` in `core.distributed_types` (4 methods)
- `TaskAssignment` in `core.distributed_types` (2 methods)
- `FailurePropagator` in `core.runtime.mesh.failure_propagator` (4 methods)
- `MeshExecutionRuntime` in `core.runtime.mesh.mesh_execution_runtime` (4 methods)
- `MeshProtocol` in `core.runtime.mesh.mesh_protocol` (7 methods)
- `MeshWorker` in `core.runtime.mesh.mesh_worker` (4 methods)
- `PeerNode` in `core.runtime.mesh.remote.discovery` (1 methods)
- `DistributedRegistry` in `core.runtime.mesh.remote.discovery` (8 methods)
- `MeshNode` in `core.runtime.mesh.remote.node` (14 methods)
- `RemoteTransportClient` in `core.runtime.mesh.remote.transport` (3 methods)
- `RemoteTransportServer` in `core.runtime.mesh.remote.transport` (4 methods)
- `_MeshRequestHandler` in `core.runtime.mesh.remote.transport` (2 methods)
- `ServiceMesh` in `core.runtime.mesh.service_mesh` (5 methods)
- `ServiceRegistry` in `core.runtime.mesh.service_registry` (8 methods)

## Placeholder Analysis

### Summary

- **Harmless:** 157
- **Suspicious:** 142
- **Runtime Critical:** 5

### Top Suspicious Files

- `core`: 142 suspicious patterns

## Thin Wrapper Analysis

### Summary

- **Total thin methods:** 684 (65.1% of all methods)
- **Pure delegates:** 55 (8.0% of thin methods)

### Highest Wrapper Ratio Classes

- **Reconciler**: 4/2 methods are thin (200%)
- **ServiceRegistry**: 16/9 methods are thin (178%)
- **DefaultContractValidator**: 2/2 methods are thin (100%)
- **DefaultComplianceValidator**: 1/1 methods are thin (100%)
- **CanonValidationResult**: 1/1 methods are thin (100%)
- **CodeGraphEventSubscriber**: 4/4 methods are thin (100%)
- **RuntimeDriftResult**: 3/3 methods are thin (100%)
- **RuntimeExecutionGraph**: 1/1 methods are thin (100%)
- **Edge**: 1/1 methods are thin (100%)
- **CodeGraph**: 6/6 methods are thin (100%)

### Worrying Pure Delegates (Orchestration Layers)

- `DefaultContractValidator.validate_inputs()` → `['ContractValidator.validate_inputs']` at `core/adapters/governance_adapter.py:9`
- `DefaultContractValidator.validate_outputs()` → `['ContractValidator.validate_outputs']` at `core/adapters/governance_adapter.py:13`
- `AdaptiveWeightEngine.check_regression()` → `['regression.detect_all']` at `core/adaptive_weights.py:252`
- `AdaptiveWeightEngine.shadow_status()` → `['shadow.status']` at `core/adaptive_weights.py:327`
- `CodeGraphEventSubscriber.stats_snapshot()` → `['_stats.snapshot']` at `core/codegraph/bridge.py:164`
- `CodeGraph.get_node()` → `['nodes.get']` at `core/codegraph/graph.py:67`
- `ExecutionTopology.get_graph()` → `['_graphs.get']` at `core/codegraph/runtime_intelligence/execution_topology.py:92`
- `ControlPlaneBrain.allocate_resources()` → `['_scheduler.allocate']` at `core/control_plane/brain.py:292`
- `ClusterManager.get_cluster()` → `['_clusters.get']` at `core/control_plane/cluster_manager.py:74`
- `RuntimeCoordinator.supervise_health()` → `['_supervisor.tick']` at `core/control_plane/coordinator.py:195`
- `HealthSupervisor.get_config()` → `['_configs.get']` at `core/control_plane/health_supervisor.py:79`
- `WorkerDrainer.drain_status()` → `['_drains.get']` at `core/control_plane/worker_drainer.py:81`
- `CostTracker.p50()` → `['self._percentile']` at `core/cost_intel.py:88`
- `CostTracker.p95()` → `['self._percentile']` at `core/cost_intel.py:92`
- `CostTracker.p99()` → `['self._percentile']` at `core/cost_intel.py:96`
- `DistributedCheckpointManager.get_completed()` → `['_local_cp.completed_nodes']` at `core/distributed_checkpoint.py:238`
- `ExecutionCore.get_event_type_for_transition()` → `['STATE_EVENT_MAP.get']` at `core/execution_core.py:132`
- `ExecutionCore.validate_transition()` → `['state.can_transition_to']` at `core/execution_core.py:140`
- `ExecutionCore.topo_sort()` → `['dag_utils.topo_sort']` at `core/execution_core.py:153`
- `ExecutionCore.independent_branches()` → `['dag_utils.independent_branches']` at `core/execution_core.py:157`

## Dead Infrastructure

- **Total modules:** 185
- **Modules with imports:** 119
- **Orphan modules (no imports):** 63

### Orphan Modules (Not Imported by Anything)

- `core.adapters.governance_adapter`
- `core.adaptive_weights`
- `core.ai_agent`
- `core.ai_context_engine`
- `core.ai_init`
- `core.ai_logging`
- `core.answer_formatter`
- `core.api_compliance`
- `core.canon.loader`
- `core.capability_negotiation`
- `core.codegraph`
- `core.codegraph.analyzer`
- `core.codegraph.builder`
- `core.codegraph.determinism`
- `core.codegraph.parser`
- `core.codegraph.runtime_intelligence.execution_topology`
- `core.codegraph.serializer`
- `core.codegraph.storage`
- `core.composition`
- `core.context_compiler`
- `core.contracts`
- `core.control_plane.cluster_manager`
- `core.cost_intel`
- `core.dag_optimizer`
- `core.dag_replay`
- `core.distributed_checkpoint`
- `core.distributed_replay`
- `core.distributed_scheduler`
- `core.distributed_types`
- `core.embedding_engine`

### Module Dependency Islands

- `core.adapters.governance_adapter` — imports nothing from core
- `core.adaptive_weights` — imports nothing from core
- `core.ai_agent` — imports nothing from core
- `core.ai_context_engine` — imports nothing from core
- `core.ai_init` — imports nothing from core
- `core.ai_logging` — imports nothing from core
- `core.answer_formatter` — imports nothing from core
- `core.api_compliance` — imports nothing from core
- `core.canon` — imports nothing from core
- `core.canon.context` — imports nothing from core
- `core.canon.loader` — imports nothing from core
- `core.canon.result` — imports nothing from core
- `core.capability_negotiation` — imports nothing from core
- `core.codegraph` — imports nothing from core
- `core.codegraph.analyzer` — imports nothing from core
- `core.codegraph.builder` — imports nothing from core
- `core.codegraph.determinism` — imports nothing from core
- `core.codegraph.drift` — imports nothing from core
- `core.codegraph.drift.drift_classifier` — imports nothing from core
- `core.codegraph.drift.metrics` — imports nothing from core

## Execution Path Validation

### ✅ Query/Planner
  Components: core.codegraph.query_engine, core.graph_query, core.query_analytics, core.query_replay
  Connected to: DAG

### ✅ DAG
  Components: core.dag_optimizer, core.dag_replay, core.dag_utils, core.models, core.models.dag
  Connected to: Query/Planner, Scheduler

### ✅ Scheduler
  Components: core.distributed_scheduler, core.interfaces.scheduler, core.scheduler, core.scheduler.resource_scheduler
  Connected to: DAG, ControlPlane (Ownership)

### ✅ ControlPlane (Ownership)
  Components: core.control_plane, core.control_plane.autoscaler, core.control_plane.brain, core.control_plane.cluster_manager, core.control_plane.coordinator
  Connected to: Scheduler, Worker/Mesh

### ✅ Worker/Mesh
  Components: core.control_plane, core.control_plane.autoscaler, core.control_plane.brain, core.control_plane.cluster_manager, core.control_plane.coordinator
  Connected to: ControlPlane (Ownership), Execution (Isolation)

### ✅ Execution (Isolation)
  Components: core.runtime.io.filesystem_isolation, core.runtime.io.network_isolation, core.runtime.isolation, core.runtime.isolation.isolation_runtime, core.runtime.sandbox
  Connected to: Worker/Mesh, Replay/Recovery

### ✅ Replay/Recovery
  Components: core.dag_replay, core.distributed_replay, core.query_replay, core.recovery_coordinator, core.replay
  Connected to: Execution (Isolation), Observability

### ✅ Observability
  Components: core.observability, core.observability.dag_visualizer, core.observability.dashboard, core.observability.failure_explorer, core.observability.timeline
  Connected to: Replay/Recovery, Feedback/Evolution

### ✅ Feedback/Evolution
  Components: core.feedback_intel, core.feedback_loop, core.runtime.evolution, core.runtime.evolution.canon_evolver, core.runtime.evolution.feedback_actuator
  Connected to: Observability

### Verdict

✅ **All layers present** — execution path is structurally complete.

## Test Integrity Analysis

- **Test files:** 55
- **Total tests:** 1388
- **Assertionless tests:** 41
- **Over-mocked files:** 3
- **Files with weak assertions:** 5

### Assertionless Tests (No Assertions)

- `test_engine_frozen_methods_exist` in `tests/test_api_compliance.py:17`
- `test_planner_frozen_methods_exist` in `tests/test_api_compliance.py:41`
- `test_engine_property_raises_before_build` in `tests/test_bootstrap.py:194`
- `test_intelligence_property_raises_before_build` in `tests/test_bootstrap.py:199`
- `test_root_property_raises_before_build` in `tests/test_bootstrap.py:204`
- `test_convenience_execute_raises_before_build` in `tests/test_bootstrap.py:216`
- `test_load_from_yaml_missing_dependency` in `tests/test_capability_security.py:157`
- `test_guard_rejects_unknown` in `tests/test_capability_security.py:288`
- `test_load_nonexistent` in `tests/test_codegraph.py:244`
- `test_check_schema_version_raises_for_unknown` in `tests/test_contracts.py:124`
- `test_register_tool_rejects_bad_version` in `tests/test_contracts.py:149`
- `test_no_available_nodes_raises` in `tests/test_control_plane_brain.py:225`
- `test_check_schema_version_raises_for_unknown` in `tests/test_execution_core.py:60`
- `test_topo_sort_cycle_detected` in `tests/test_execution_core.py:142`
- `test_call_no_handler_raises` in `tests/test_gaps_1_4.py:146`

### Over-Mocked Test Files

- `tests/test_context_compiler.py` — 13 mocks (ratio: 0.085)
- `tests/test_execution_runtime.py` — 9 mocks (ratio: 0.045)
- `tests/test_mesh_runtime.py` — 9 mocks (ratio: 0.042)

## Subsystem Confidence Assessment

Scale: 0 (fake/totally broken) → 10 (fully real and connected)

- **F1 — RuntimeOS API:** ░░░░░░░░░░ 0/10
  - ⚠ thin_wrapper:engine
  - ⚠ thin_wrapper:brain
  - ⚠ thin_wrapper:control
  - ⚠ thin_wrapper:isolation
  - ⚠ thin_wrapper:mesh

- **F2 — Control Plane:** ░░░░░░░░░░ 0/10
  - ⚠ thin_wrapper:config
  - ⚠ thin_wrapper:record_scaling
  - ⚠ thin_wrapper:scaling_history
  - ⚠ thin_wrapper:reset_cooldown
  - ⚠ thin_wrapper:state

- **F3 — Resource Scheduler:** ░░░░░░░░░░ 0/10

- **F4 — Observability:** ░░░░░░░░░░ 0/10

- **Execution Engine:** ░░░░░░░░░░ 0/10

- **Mesh/Distributed:** ░░░░░░░░░░ 0/10

- **Sandbox/Isolation:** ░░░░░░░░░░ 0/10

- **Secrets/Security:** ░░░░░░░░░░ 0/10

- **Tests:** ░░░░░░░░░░ 0/10
  - ⚠ assertionless:41
  - ⚠ over_mocked:3
  - ⚠ weak_assertions:5

## Overall Confidence Score

**░░░░░░░░░░ 0.0/10**

## Final Verdict

**The system has serious reality problems.**
Multiple execution layers are missing or disconnected. The architecture
resembles a facade more than a runtime. Recommend fundamental
re-architecture before relying on this system.

---
_This report was generated by the Architecture Reality Auditor._
_It assumes malicious compliance and trusts no naming, comments, or tests._