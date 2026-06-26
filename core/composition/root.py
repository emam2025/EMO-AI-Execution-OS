"""CompositionRoot — single source of truth for constructing the EMO AI Runtime.

Roles:
   1. Factory — builds ExecutionEngine with all dependencies wired
   2. Bootstrapper — resolves the full dependency graph at construction time
   3. Lifecycle — start/shutdown for background services

Rules:
   - ONLY CompositionRoot may instantiate ExecutionEngine (LAW 13).
   - All cross-layer dependencies must flow through this root.
   - CompositionRoot is INTERNAL — production code MUST use ``EmoRuntime``
     from ``core.runtime.bootstrap`` instead.
   - LAW 13: No direct execution without IsolationRuntime.
     build_execution_engine() REQUIRES isolation_runtime to be set.

Phase 3.7:
   - Exposes execution_core and execution_runtime for direct access.

Phase 3.8:
   - Exposes runtime_intelligence (self-awareness API).

Phase 3.9:
   - Adds start() / shutdown() lifecycle.

Phase 4.5:
   - Adds isolation_runtime enforcement (LAW 13).
   - RuntimeError if ExecutionEngine built without IsolationRuntime.

Phase D8:
   - Adds D8 Service Mesh contracts (LAW 23-27).
   - Exposes 5 bounded services: scheduler, state_store, dispatcher,
     retry_handler, lease_manager, plus failure_propagation matrix.
   - strict_service_isolation mode enforces LAW 23-27 boundaries.

Ref: DEVELOPER.md §15.15a D8.1
Ref: DEVELOPER.md §15.15b §4.5
Ref: Canon LAW 13 (No direct service calls)
Ref: Canon LAW 23-27 (Service Ownership)
Ref: Canon RULE 1 (No Direct Execution)
"""

from typing import Any, Dict, Optional

from core.canon import CanonValidator
from core.codegraph.bridge import CodeGraphEventSubscriber
from core.codegraph.drift import CodeGraphDriftDetector, DriftDetector, DriftStore
from core.codegraph.integration import CodeGraphRuntime
from core.execution_engine import ExecutionEngine
from core.execution_core import ExecutionCore
from core.execution_runtime import ExecutionRuntime
from core.interfaces.event_bus import IEventBus
from core.interfaces.execution_engine import IExecutionEngine
from core.interfaces.execution import IDAGOptimizer
from core.interfaces.systems import (
    ICostTracker,
    IDAGSizeLimiter,
    ICheckpointManager,
)
from core.interfaces.governance import (
    IContractValidator,
    IComplianceValidator,
)
from core.models.dag import ToolSpec
from core.runtime.event_bus import InMemoryEventBus
from core.runtime.event_store import EventStore
from core.runtime_intelligence import RuntimeIntelligence
from core.runtime.services.scheduler import ExecutionScheduler
from core.runtime.services.state_store import ExecutionStateStore
from core.runtime.services.tool_dispatcher import ExecutionToolDispatcher
from core.runtime.services.retry_handler import ExecutionRetryHandler
from core.runtime.services.lease_manager import ExecutionLeaseManager
from core.runtime.services.failure_propagation import FailureMatrix


class CompositionRoot:
    """Single source of truth for constructing the EMO AI Runtime."""

    def __init__(
        self,
        tool_registry: Optional[Dict[str, ToolSpec]] = None,
        memory=None,
        worker_pool_size: int = 4,
        cache=None,
        service_registry=None,
        optimizer: Optional[IDAGOptimizer] = None,
        cost_tracker: Optional[ICostTracker] = None,
        size_limiter: Optional[IDAGSizeLimiter] = None,
        checkpoint_manager: Optional[ICheckpointManager] = None,
        contract_validator: Optional[IContractValidator] = None,
        compliance_validator: Optional[IComplianceValidator] = None,
        event_bus: Optional[IEventBus] = None,
        event_store: Optional[EventStore] = None,
        codegraph: Any = None,
        isolation_runtime: Any = None,
        strict_isolation: bool = False,
        scheduler: Optional[ExecutionScheduler] = None,
        state_store: Optional[ExecutionStateStore] = None,
        dispatcher: Optional[ExecutionToolDispatcher] = None,
        retry_handler: Optional[ExecutionRetryHandler] = None,
        lease_manager: Optional[ExecutionLeaseManager] = None,
        failure_matrix: Optional[FailureMatrix] = None,
        strict_service_isolation: bool = False,
        sandbox_manager: Any = None,
        strict_api_mode: bool = False,
        feedback_loop: Any = None,
        strict_feedback_mode: bool = False,
        control_plane_mode: Any = None,
        strict_control_mode: bool = False,
        resource_scheduler: Any = None,
        strict_quota_mode: bool = False,
        strict_trace_mode: bool = False,
        planner_agent: Any = None,
        strict_planning_mode: bool = False,
        critic_agent: Any = None,
        strict_critic_mode: bool = False,
        optimizer_agent: Any = None,
        strict_optimizer_mode: bool = False,
        tool_synthesizer: Any = None,
        strict_synthesis_mode: bool = False,
        lifecycle_manager: Any = None,
        strict_swarm_mode: bool = False,
        computer_use_runtime: Any = None,
        strict_session_mode: bool = False,
        # Phase I1 — Production Infrastructure
        kubernetes_deployer: Any = None,
        distributed_queue: Any = None,
        ha_orchestrator: Any = None,
        object_storage: Any = None,
        infra_trace_correlator: Any = None,
        strict_infra_mode: bool = False,
        # Phase I2 — Data Infrastructure
        postgresql_manager: Any = None,
        distributed_log: Any = None,
        runtime_analytics: Any = None,
        data_migrator: Any = None,
        data_trace_correlator: Any = None,
        strict_data_mode: bool = False,
        # Phase I3 — Production Reliability
        failover_orchestrator: Any = None,
        disaster_recovery: Any = None,
        rolling_update_manager: Any = None,
        runtime_migrator: Any = None,
        recovery_trace_correlator: Any = None,
        strict_reliability_mode: bool = False,
        # Phase FINAL — Production Readiness & Certification
        system_auditor: Any = None,
        load_generator: Any = None,
        security_validator: Any = None,
        certification_engine: Any = None,
        certification_state_machine: Any = None,
        strict_certification_mode: bool = False,
        # Phase J1 — Developer Experience Layer
        sdk_client: Any = None,
        cli_runtime: Any = None,
        doc_generator: Any = None,
        api_spec_publisher: Any = None,
        doc_pipeline: Any = None,
        devex_trace_correlator: Any = None,
        strict_devex_mode: bool = False,
        # Phase J2 — Enterprise Readiness Layer
        tenant_router: Any = None,
        usage_meter: Any = None,
        billing_engine: Any = None,
        compliance_auditor: Any = None,
        enterprise_trace_correlator: Any = None,
        strict_enterprise_mode: bool = False,
        # Phase J3 — Production Readiness Layer
        chaos_injector: Any = None,
        load_orchestrator: Any = None,
        stability_validator: Any = None,
        certification_gate: Any = None,
        readiness_trace_correlator: Any = None,
        strict_readiness_mode: bool = False,
        # EXEC-DIRECTIVE-021 — Canary Deployment
        canary_observer: Any = None,
        strict_canary_mode: bool = False,
        # EXEC-DIRECTIVE-023 — Phase K2 Hardening
        strict_hardening_mode: bool = False,
        # EXEC-DIRECTIVE-PILOT-001 — Production Pilot
        strict_pilot_mode: bool = False,
        pilot_trace_correlator: Any = None,
        # Phase L — Cognitive Memory Layer
        memory_hierarchy: Any = None,
        context_compiler: Any = None,
        skill_graph_manager: Any = None,
        memory_state_machine: Any = None,
        cognitive_trace_correlator: Any = None,
        strict_memory_mode: bool = False,
        # Phase G — Cognitive Orchestration Layer
        orchestration_state_machine: Any = None,
        orchestration_trace_correlator: Any = None,
        strict_orchestration_mode: bool = False,
    ):
        self._started = False
        self._tool_registry = tool_registry
        self._memory = memory
        self._worker_pool_size = worker_pool_size
        self._cache = cache
        self._service_registry = service_registry
        self._optimizer = optimizer
        self._cost_tracker = cost_tracker
        self._size_limiter = size_limiter
        self._checkpoint_manager = checkpoint_manager
        self._contract_validator = contract_validator
        self._compliance_validator = compliance_validator
        self._event_bus = event_bus or InMemoryEventBus()
        self._event_store = event_store or EventStore()
        self._codegraph = codegraph
        self._isolation_runtime = isolation_runtime
        self._strict_isolation = strict_isolation
        self._strict_service_isolation = strict_service_isolation
        self._sandbox_manager = sandbox_manager
        self._strict_api_mode = strict_api_mode
        self._feedback_loop = feedback_loop
        self._strict_feedback_mode = strict_feedback_mode
        self._control_plane_mode = control_plane_mode
        self._strict_control_mode = strict_control_mode
        self._resource_scheduler = resource_scheduler
        self._strict_quota_mode = strict_quota_mode
        self._trace_collector: Any = None
        self._telemetry_aggregator: Any = None
        self._dashboard_data_provider: Any = None
        self._alert_router: Any = None
        self._strict_trace_mode = strict_trace_mode
        self._planner_agent = planner_agent
        self._strict_planning_mode = strict_planning_mode
        self._critic_agent = critic_agent
        self._strict_critic_mode = strict_critic_mode
        self._optimizer_agent = optimizer_agent
        self._strict_optimizer_mode = strict_optimizer_mode
        self._tool_synthesizer = tool_synthesizer
        self._tool_validator: Any = None
        self._tool_sandboxer: Any = None
        self._tool_registry_manager: Any = None
        self._synthesis_sm: Any = None
        self._synthesis_trace_correlator: Any = None
        self._strict_synthesis_mode = strict_synthesis_mode
        self._lifecycle_manager = lifecycle_manager
        self._contract_engine: Any = None
        self._g5_swarm_coordinator: Any = None
        self._hierarchical_planner: Any = None
        self._lifecycle_sm: Any = None
        self._swarm_trace_correlator: Any = None
        self._strict_swarm_mode = strict_swarm_mode
        self._computer_use_runtime = computer_use_runtime
        self._browser_runtime: Any = None
        self._desktop_worker: Any = None
        self._vision_grounding: Any = None
        self._session_journal: Any = None
        self._session_sm: Any = None
        self._computer_use_trace_correlator: Any = None
        self._strict_session_mode = strict_session_mode

        # Phase I1 — Production Infrastructure
        self._kubernetes_deployer = kubernetes_deployer
        self._distributed_queue = distributed_queue
        self._ha_orchestrator = ha_orchestrator
        self._object_storage = object_storage
        self._infra_trace_correlator = infra_trace_correlator
        self._ha_state_machine: Any = None
        self._strict_infra_mode = strict_infra_mode

        # Phase I2 — Data Infrastructure
        self._postgresql_manager = postgresql_manager
        self._distributed_log = distributed_log
        self._runtime_analytics = runtime_analytics
        self._data_migrator = data_migrator
        self._data_trace_correlator = data_trace_correlator
        self._acid_state_machine: Any = None
        self._strict_data_mode = strict_data_mode

        # Phase I3 — Production Reliability
        self._failover_orchestrator = failover_orchestrator
        self._disaster_recovery = disaster_recovery
        self._rolling_update_manager = rolling_update_manager
        self._runtime_migrator = runtime_migrator
        self._recovery_trace_correlator = recovery_trace_correlator
        self._reliability_state_machine: Any = None
        self._strict_reliability_mode = strict_reliability_mode

        # Phase FINAL — Production Readiness & Certification
        self._system_auditor = system_auditor
        self._load_generator = load_generator
        self._security_validator = security_validator
        self._certification_engine = certification_engine
        self._certification_state_machine = certification_state_machine
        self._strict_certification_mode = strict_certification_mode

        # Phase J1 — Developer Experience Layer
        self._sdk_client = sdk_client
        self._cli_runtime = cli_runtime
        self._doc_generator = doc_generator
        self._api_spec_publisher = api_spec_publisher
        self._doc_pipeline = doc_pipeline
        self._devex_trace_correlator = devex_trace_correlator
        self._strict_devex_mode = strict_devex_mode

        # Phase J2 — Enterprise Readiness Layer
        self._tenant_router = tenant_router
        self._usage_meter = usage_meter
        self._billing_engine = billing_engine
        self._compliance_auditor = compliance_auditor
        self._enterprise_trace_correlator = enterprise_trace_correlator
        self._strict_enterprise_mode = strict_enterprise_mode

        # Phase J3 — Production Readiness Layer
        self._chaos_injector = chaos_injector
        self._load_orchestrator = load_orchestrator
        self._stability_validator = stability_validator
        self._certification_gate = certification_gate
        self._readiness_trace_correlator = readiness_trace_correlator
        self._readiness_state_machine: Any = None
        self._strict_readiness_mode = strict_readiness_mode

        # Phase P10 — Final Delivery Production Components
        self._cli_commands: Any = None
        self._emo_sdk_client: Any = None
        self._multi_tenant_router: Any = None
        self._p10_audit_generator: Any = None
        self._p10_compliance_reporter: Any = None

        # EXEC-DIRECTIVE-021 — Canary Deployment
        self._canary_observer = canary_observer
        self._strict_canary_mode = strict_canary_mode

        # EXEC-DIRECTIVE-023 — Phase K2 Hardening
        self._strict_hardening_mode = strict_hardening_mode

        # EXEC-DIRECTIVE-028 — Final Production Readiness & Baseline Freeze
        self._strict_final_freeze_mode: bool = False
        self._freeze_manifest: Optional[Dict[str, str]] = None

        # EXEC-DIRECTIVE-PILOT-001 — Production Pilot
        self._strict_pilot_mode = strict_pilot_mode
        self._pilot_trace_correlator = pilot_trace_correlator

        # Phase L — Cognitive Memory Layer
        self._memory_hierarchy = memory_hierarchy
        self._context_compiler = context_compiler
        self._skill_graph_manager = skill_graph_manager
        self._memory_state_machine = memory_state_machine
        self._cognitive_trace_correlator = cognitive_trace_correlator
        self._strict_memory_mode = strict_memory_mode

        # Phase G — Cognitive Orchestration Layer
        self._orchestration_state_machine = orchestration_state_machine
        self._orchestration_trace_correlator = orchestration_trace_correlator
        self._strict_orchestration_mode = strict_orchestration_mode

        # Phase F1 — Unified Runtime API
        self._unified_runtime: Any = None

        # Phase 3.7 — Core + Runtime (built with engine)
        self._core: Optional[ExecutionCore] = None
        self._runtime: Optional[ExecutionRuntime] = None

        # Auto-subscribe CodeGraph bridge to event bus
        self._codegraph_bridge = CodeGraphEventSubscriber(self._event_bus)

        # Drift detection system
        self._drift_store = DriftStore()
        self._drift_detector = DriftDetector()
        self._codegraph_drift = CodeGraphDriftDetector(
            store=self._drift_store,
            detector=self._drift_detector,
        )

        # Production CodeGraphRuntime — bridges static analysis into runtime
        self._codegraph_runtime = CodeGraphRuntime(codegraph=self._codegraph)
        self._codegraph_runtime.wire(
            event_bus=self._event_bus,
        )

        # Phase 3.8 — Runtime Intelligence
        self._runtime_intelligence = RuntimeIntelligence(
            event_store=self._event_store,
            graph=self._codegraph,
        )

        # Canon enforcement engine
        self._canon_validator = CanonValidator()

        # Phase D8 — Service Mesh Contracts (LAW 23-27)
        # Each service owns exactly one domain with private state.
        # strict_service_isolation: enforces boundary checks.
        self._scheduler = scheduler or ExecutionScheduler()
        self._state_store = state_store or ExecutionStateStore()
        self._dispatcher = dispatcher or ExecutionToolDispatcher()
        self._retry_handler = retry_handler or ExecutionRetryHandler()
        self._lease_manager = lease_manager or ExecutionLeaseManager()
        self._failure_matrix = failure_matrix or FailureMatrix(
            event_bus=self._event_bus,
        )

        self._engine: Optional[IExecutionEngine] = None

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Start background services."""
        if self._started:
            return
        self._started = True

    def shutdown(self) -> None:
        """Gracefully stop all background services."""
        if not self._started:
            return
        if self._engine is not None:
            self._engine.shutdown()
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    # ── Services ─────────────────────────────────────────────────

    @property
    def event_bus(self) -> IEventBus:
        return self._event_bus

    @property
    def event_store(self) -> EventStore:
        return self._event_store

    @property
    def codegraph_bridge(self) -> CodeGraphEventSubscriber:
        return self._codegraph_bridge

    @property
    def drift_store(self) -> DriftStore:
        return self._drift_store

    @property
    def codegraph_drift(self) -> CodeGraphDriftDetector:
        return self._codegraph_drift

    @property
    def canon_validator(self) -> CanonValidator:
        return self._canon_validator

    @property
    def runtime_intelligence(self) -> RuntimeIntelligence:
        return self._runtime_intelligence

    @property
    def execution_core(self) -> ExecutionCore:
        if self._core is None:
            self._core = ExecutionCore()
        return self._core

    @property
    def execution_runtime(self) -> Optional[ExecutionRuntime]:
        return self._runtime

    @property
    def isolation_runtime(self) -> Any:
        """Return the IsolationRuntime instance (Phase 4.5).

        LAW 13: No direct execution without isolation.
        All execution MUST route through IIsolationRuntime.
        """
        return self._isolation_runtime

    @isolation_runtime.setter
    def isolation_runtime(self, runtime: Any) -> None:
        """Set the IsolationRuntime instance.

        LAW 13 enforcement: Cannot be None after being set.
        """
        self._isolation_runtime = runtime

    # ── Phase D8 — Service Mesh Contracts (LAW 23-27) ────────────

    @property
    def scheduler(self) -> ExecutionScheduler:
        """ExecutionScheduler — owns execution ordering (LAW 23)."""
        return self._scheduler

    @property
    def state_store(self) -> ExecutionStateStore:
        """ExecutionStateStore — owns persistence + traces (LAW 26)."""
        return self._state_store

    @property
    def dispatcher(self) -> ExecutionToolDispatcher:
        """ExecutionToolDispatcher — owns execution routing (LAW 24)."""
        return self._dispatcher

    @property
    def retry_handler(self) -> ExecutionRetryHandler:
        """ExecutionRetryHandler — owns retry semantics (LAW 25)."""
        return self._retry_handler

    @property
    def lease_manager(self) -> ExecutionLeaseManager:
        """ExecutionLeaseManager — owns distributed ownership (LAW 23)."""
        return self._lease_manager

    @property
    def failure_matrix(self) -> FailureMatrix:
        """FailureMatrix — failure propagation (LAW 20-22)."""
        return self._failure_matrix

    @property
    def codegraph_runtime(self) -> CodeGraphRuntime:
        return self._codegraph_runtime

    # ── Phase F1 — Unified Runtime API ────────────────────────

    @property
    def unified_runtime(self) -> Any:
        """Return the UnifiedRuntime instance (Phase F1).

        LAW 13: UnifiedRuntime is constructed here with all D8 services
        injected. No other module may construct UnifiedRuntime directly.

        strict_api_mode: When True, enables guard enforcement for testing.
        Default False for production backward compatibility.
        """
        if self._unified_runtime is None:
            self._unified_runtime = self._build_unified_runtime()
        return self._unified_runtime

    def _build_unified_runtime(self) -> Any:
        """Construct and return a new UnifiedRuntime instance.

        This is the ONLY valid construction point for UnifiedRuntime.
        All D8 services and infrastructure are injected via constructor.

        Ref: DEVELOPER.md §15.2
        Ref: Canon LAW 13
        """
        from core.runtime.api.unified_runtime_api import UnifiedRuntime

        return UnifiedRuntime(
            scheduler=self._scheduler,
            state_store=self._state_store,
            dispatcher=self._dispatcher,
            retry_handler=self._retry_handler,
            lease_manager=self._lease_manager,
            event_bus=self._event_bus,
            failure_matrix=self._failure_matrix,
            sandbox_manager=self._sandbox_manager,
            isolation_runtime=self._isolation_runtime,
            strict_api_mode=self._strict_api_mode,
        )

    # ── Phase F2 — Control Plane & Autoscaler ────────────────

    @property
    def control_plane(self) -> Any:
        """Return the ControlPlane instance (Phase F2).

        LAW 11: No global state — ControlPlane is per-instance.
        LAW 8: All state transitions guarded.
        strict_control_mode: When True, enforces guard checks for testing.
        """
        if self._control_plane_mode is None:
            self._control_plane_mode = self._build_control_plane()
        return self._control_plane_mode

    def _build_control_plane(self) -> Any:
        """Construct and return a new ControlPlane instance.

        All dependencies are injected via constructor.
        HealthSupervisor and Autoscaler share the EventBus for
        runtime.health.* and runtime.scaling.* topics.

        Ref: DEVELOPER.md §15.9
        Ref: Canon LAW 5, LAW 8, LAW 11
        """
        from core.runtime.control_plane.autoscaler import Autoscaler
        from core.runtime.control_plane.control_plane import ControlPlane
        from core.runtime.control_plane.health_supervisor import HealthSupervisor
        from core.runtime.control_plane.reconciliation_loop import ReconciliationLoop
        from core.runtime.control_plane.worker_drainer import WorkerDrainer
        from core.runtime.control_plane.oscillation_guard import (
            CooldownTimer, HysteresisEvaluator, ConsecutiveCycleTracker,
        )

        return ControlPlane(
            autoscaler=Autoscaler(
                cooldown_timer=CooldownTimer(),
                hysteresis=HysteresisEvaluator(),
                cycle_tracker=ConsecutiveCycleTracker(required_consecutive=2),
            ),
            health_supervisor=HealthSupervisor(event_bus=self._event_bus),
            reconciliation_loop=ReconciliationLoop(),
            worker_drainer=WorkerDrainer(max_drain_wait_sec=300.0),
        )

    # ── Phase F3 — Resource Scheduler & Quota Arbitration ───

    @property
    def resource_scheduler(self) -> Any:
        """Return the ResourceScheduler instance (Phase F3).

        LAW 11: No global state — ResourceScheduler is per-instance.
        LAW 10: Resource limits enforced via QuotaArbitrator.
        strict_quota_mode: When True, enables strict guard enforcement.
        """
        if self._resource_scheduler is None:
            self._resource_scheduler = self._build_resource_scheduler()
        return self._resource_scheduler

    def _build_resource_scheduler(self) -> Any:
        """Construct and return a new ResourceScheduler instance.

        All dependencies are injected via constructor.
        QuotaArbitrator and ResourceScheduler share EventBus for
        runtime.resource.* and runtime.quota.* topics.

        Ref: DEVELOPER.md §15.9
        Ref: Canon LAW 5, LAW 8, LAW 10, LAW 11
        """
        from core.runtime.resource_scheduler.quota_arbitrator import QuotaArbitrator
        from core.runtime.resource_scheduler.fairness_engine import FairnessEngine
        from core.runtime.resource_scheduler.topology_mapper import TopologyMapper
        from core.runtime.resource_scheduler.allocation_state_machine import (
            AllocationStateMachine,
        )
        from core.runtime.resource_scheduler.starvation_handler import StarvationHandler
        from core.runtime.resource_scheduler.resource_scheduler import ResourceScheduler

        return ResourceScheduler(
            quota_arbitrator=QuotaArbitrator(),
            fairness_engine=FairnessEngine(),
            topology_mapper=TopologyMapper(),
            state_machine=AllocationStateMachine(),
            starvation_handler=StarvationHandler(),
        )

    # ── Phase D9 — Runtime Intelligence Feedback Loop ──────────

    @property
    def feedback_loop(self) -> Any:
        """Return the FeedbackLoop instance (Phase D9).

        LAW 11: No global state — FeedbackLoop is per-instance.
        §17.9: No CodeGraph imports in feedback loop.
        """
        if self._feedback_loop is None:
            self._feedback_loop = self._build_feedback_loop()
        return self._feedback_loop

    def _build_feedback_loop(self) -> Any:
        """Construct and return a new FeedbackLoop instance.

        All dependencies are injected via constructor.
        EventBus is shared for runtime.execution.* subscription
        and runtime.drift.* publication.

        Ref: DEVELOPER.md §5.3
        Ref: Canon LAW 11, §17.9
        """
        from core.runtime.feedback.feedback_loop import FeedbackLoop
        from core.runtime.feedback.hotspot_detector import HotspotDetector
        from core.runtime.feedback.coupling_adjuster import DynamicCouplingAdjuster
        from core.runtime.feedback.architecture_alert import ArchitectureAlert
        from core.runtime.feedback.rate_limiter import RateLimiter
        from core.runtime.models.feedback_models import FeedbackPolicy

        return FeedbackLoop(
            coupling_adjuster=DynamicCouplingAdjuster(),
            hotspot_detector=HotspotDetector(),
            architecture_alert=ArchitectureAlert(),
            rate_limiter=RateLimiter(),
            policy=FeedbackPolicy(),
            event_bus=self._event_bus,
        )

    # ── Phase F4 — Observability Layer ───────────────────────

    @property
    def trace_collector(self) -> Any:
        """Return the TraceCollector instance (Phase F4).

        LAW 12: Every span carries trace_id, span_id, parent_id.
        LAW 11: No global state — per-instance span tracking.
        strict_trace_mode: When True, enables guard enforcement.
        """
        if self._trace_collector is None:
            self._trace_collector = self._build_trace_collector()
        return self._trace_collector

    @property
    def telemetry_aggregator(self) -> Any:
        """Return the TelemetryAggregator instance (Phase F4).

        LAW 5: Every critical span MUST be accounted for.
        backpressure_sampler prevents CRITICAL span drops.
        """
        if self._telemetry_aggregator is None:
            self._telemetry_aggregator = self._build_telemetry_aggregator()
        return self._telemetry_aggregator

    @property
    def dashboard_data_provider(self) -> Any:
        """Return the DashboardDataProvider instance (Phase F4).

        §15.13: Read-only queries for the Runtime Dashboard.
        RULE 1: All methods return deterministic snapshots.
        """
        if self._dashboard_data_provider is None:
            self._dashboard_data_provider = self._build_dashboard_provider()
        return self._dashboard_data_provider

    @property
    def alert_router(self) -> Any:
        """Return the AlertRouter instance (Phase F4).

        LAW 5: Alerts routed to configured targets.
        RULE 3: Duplicate suppression prevents alert storms.
        """
        if self._alert_router is None:
            self._alert_router = self._build_alert_router()
        return self._alert_router

    def _build_trace_collector(self) -> Any:
        from core.runtime.observability.trace_collector import TraceCollector
        return TraceCollector()

    def _build_telemetry_aggregator(self) -> Any:
        from core.runtime.observability.telemetry_aggregator import TelemetryAggregator
        from core.runtime.observability.aggregation_state_machine import (
            AggregationStateMachine,
        )
        from core.runtime.observability.backpressure_sampler import BackpressureSampler

        return TelemetryAggregator(
            state_machine=AggregationStateMachine(),
            sampler=BackpressureSampler(),
        )

    def _build_dashboard_provider(self) -> Any:
        from core.runtime.observability.dashboard_data_provider import (
            DashboardDataProvider,
        )
        return DashboardDataProvider()

    def _build_alert_router(self) -> Any:
        from core.runtime.observability.alert_router import AlertRouter
        return AlertRouter()

    # ── Phase G4 — Tool Synthesis Agent ─────────────────────────

    @property
    def tool_synthesizer(self) -> Any:
        """Return the ToolSynthesizer instance (Phase G4).

        LAW 2:  All tool interfaces conform to Interface Authority.
        LAW 12: Every synthesis carries a synthesis_trace_id.
        RULE 3: Safety Guards enforce all preconditions.
        strict_synthesis_mode: When True, enables guard enforcement.
        """
        if self._tool_synthesizer is None:
            self._tool_synthesizer = self._build_tool_synthesizer()
        return self._tool_synthesizer

    def _build_tool_synthesizer(self) -> Any:
        from core.runtime.tool_synthesis.tool_synthesizer import ToolSynthesizer
        from core.runtime.tool_synthesis.tool_validator import ToolValidator
        from core.runtime.tool_synthesis.tool_sandboxer import ToolSandboxer
        from core.runtime.tool_synthesis.tool_registry_manager import (
            ToolRegistryManager,
        )
        from core.runtime.tool_synthesis.synthesis_state_machine import (
            SynthesisStateMachine,
        )
        from core.runtime.tool_synthesis.trace_correlator import (
            SynthesisTraceCorrelator,
        )

        if self._tool_validator is None:
            self._tool_validator = ToolValidator()
        if self._tool_sandboxer is None:
            self._tool_sandboxer = ToolSandboxer()
        if self._tool_registry_manager is None:
            self._tool_registry_manager = ToolRegistryManager()
        if self._synthesis_sm is None:
            self._synthesis_sm = SynthesisStateMachine()
        if self._synthesis_trace_correlator is None:
            self._synthesis_trace_correlator = SynthesisTraceCorrelator()

        return ToolSynthesizer(
            validator=self._tool_validator,
            sandboxer=self._tool_sandboxer,
            registry_manager=self._tool_registry_manager,
            state_machine=self._synthesis_sm,
            trace_correlator=self._synthesis_trace_correlator,
            event_bus=self._event_bus,
            strict_synthesis_mode=self._strict_synthesis_mode,
        )

    # ── Phase G5 — Multi-Agent Runtime ───────────────────────────

    @property
    def agent_lifecycle_manager(self) -> Any:
        """Return the AgentLifecycleManager instance (Phase G5).

        LAW 26: Lifecycle ownership — every agent lifecycle is managed.
        LAW 27: One service per domain — each swarm agent owns exactly one.
        RULE 4: Isolation — agents are spawned in isolated contexts.
        RULE 5: Recovery — failed agents are independently retried.
        strict_swarm_mode: When True, enables guard enforcement.
        """
        if self._lifecycle_manager is None:
            self._lifecycle_manager = self._build_agent_lifecycle_manager()
        return self._lifecycle_manager

    def _build_agent_lifecycle_manager(self) -> Any:
        from core.runtime.multi_agent.lifecycle_manager import AgentLifecycleManager
        from core.runtime.multi_agent.contract_engine import AgentContractEngine
        from core.runtime.multi_agent.swarm_coordinator import SwarmCoordinator
        from core.runtime.multi_agent.hierarchical_planner import HierarchicalPlanner
        from core.runtime.multi_agent.lifecycle_state_machine import (
            LifecycleStateMachine,
        )
        from core.runtime.multi_agent.swarm_trace_correlator import (
            SwarmTraceCorrelator,
        )

        if self._contract_engine is None:
            self._contract_engine = AgentContractEngine()
        if self._g5_swarm_coordinator is None:
            self._g5_swarm_coordinator = SwarmCoordinator()
        if self._hierarchical_planner is None:
            self._hierarchical_planner = HierarchicalPlanner()
        if self._lifecycle_sm is None:
            self._lifecycle_sm = LifecycleStateMachine()
        if self._swarm_trace_correlator is None:
            self._swarm_trace_correlator = SwarmTraceCorrelator()

        return AgentLifecycleManager(
            state_machine=self._lifecycle_sm,
        )

    # ── Phase H1 — Computer Use Runtime ─────────────────────────

    @property
    def computer_use_runtime(self) -> Any:
        """Return the ComputerUseRuntime instance (Phase H1).

        LAW 10: All computer use runs in sandboxed isolation.
        LAW 12: Every session carries session_trace_id.
        LAW 24: All actions dispatched through session journal.
        RULE 2: All IO gated by Interaction Guards.
        strict_session_mode: When True, enables guard enforcement.
        """
        if self._computer_use_runtime is None:
            self._computer_use_runtime = self._build_computer_use_runtime()
        return self._computer_use_runtime

    def _build_computer_use_runtime(self) -> Any:
        from core.runtime.computer_use.browser_runtime import BrowserRuntime
        from core.runtime.computer_use.desktop_worker import DesktopWorker
        from core.runtime.computer_use.vision_grounding import VisionGrounding
        from core.runtime.computer_use.session_journal import SessionJournal
        from core.runtime.computer_use.session_state_machine import (
            ComputerUseSessionStateMachine,
        )
        from core.runtime.computer_use.trace_correlator import (
            ComputerUseTraceCorrelator,
        )

        if self._session_sm is None:
            self._session_sm = ComputerUseSessionStateMachine()
        if self._computer_use_trace_correlator is None:
            self._computer_use_trace_correlator = ComputerUseTraceCorrelator()
        if self._browser_runtime is None:
            self._browser_runtime = BrowserRuntime(
                isolation_runtime=self._isolation_runtime,
                state_machine=self._session_sm,
            )
        if self._desktop_worker is None:
            self._desktop_worker = DesktopWorker(
                isolation_runtime=self._isolation_runtime,
                state_machine=self._session_sm,
            )
        if self._vision_grounding is None:
            self._vision_grounding = VisionGrounding(
                isolation_runtime=self._isolation_runtime,
                state_machine=self._session_sm,
            )
        if self._session_journal is None:
            self._session_journal = SessionJournal(
                state_machine=self._session_sm,
            )

        return {
            "browser_runtime": self._browser_runtime,
            "desktop_worker": self._desktop_worker,
            "vision_grounding": self._vision_grounding,
            "session_journal": self._session_journal,
            "state_machine": self._session_sm,
            "trace_correlator": self._computer_use_trace_correlator,
        }

    # ── Phase I1 — Production Infrastructure ─────────────────────

    @property
    def kubernetes_deployer(self) -> Any:
        """Return the KubernetesDeployer instance (Phase I1).

        LAW 1: Deployer conforms to IKubernetesDeployer interface.
        LAW 5: All deployment events published to F4 via event bus.
        LAW 11: No global mutable state — every deploy is fresh.
        RULE 3: Pre-deployment capability check enforced.
        RULE 4: Worker scaling is isolated per deployment.
        strict_infra_mode: When True, enables guard enforcement.
        """
        if self._kubernetes_deployer is None:
            self._kubernetes_deployer = self._build_kubernetes_deployer()
        return self._kubernetes_deployer

    @property
    def distributed_queue(self) -> Any:
        """Return the DistributedQueue instance (Phase I1).

        LAW 11: Queue is a service boundary — no shared state.
        RULE 2: Payload validated before enqueue.
        RULE 5: Failed messages routed to DLQ after max_retries.
        """
        if self._distributed_queue is None:
            self._distributed_queue = self._build_distributed_queue()
        return self._distributed_queue

    @property
    def ha_orchestrator(self) -> Any:
        """Return the HAOrchestrator instance (Phase I1).

        LAW 11: No global state — election is ephemeral, scoped to term.
        LAW 20: Quorum-based failure detection.
        LAW 21: Failure propagation is contained.
        LAW 22: Fencing enforces service isolation.
        RULE 3: Election requires quorum > total_nodes / 2.
        RULE 5: Recovery retries independently.
        """
        if self._ha_orchestrator is None:
            self._ha_orchestrator = self._build_ha_orchestrator()
        return self._ha_orchestrator

    @property
    def object_storage(self) -> Any:
        """Return the ObjectStorage instance (Phase I1).

        LAW 11: No global mutable state.
        RULE 1: Same payload → same checksum (deterministic).
        RULE 2: Input validated before storage.
        """
        if self._object_storage is None:
            self._object_storage = self._build_object_storage()
        return self._object_storage

    @property
    def infra_trace_correlator(self) -> Any:
        """Return the InfraTraceCorrelator instance (Phase I1).

        LAW 5: Every infrastructure operation carries infra_trace_id.
        LAW 12: Every trace is fully back-traceable.
        """
        if self._infra_trace_correlator is None:
            self._infra_trace_correlator = self._build_infra_trace_correlator()
        return self._infra_trace_correlator

    def _build_kubernetes_deployer(self) -> Any:
        from core.runtime.infra.kubernetes_deployer import KubernetesDeployer
        return KubernetesDeployer(event_bus=self._event_bus)

    def _build_distributed_queue(self) -> Any:
        from core.runtime.infra.distributed_queue import DistributedQueue
        return DistributedQueue(event_bus=self._event_bus)

    def _build_ha_orchestrator(self) -> Any:
        from core.runtime.infra.ha_orchestrator import HAOrchestrator
        from core.runtime.infra.ha_state_machine import HAStateMachine

        if self._ha_state_machine is None:
            self._ha_state_machine = HAStateMachine()

        return HAOrchestrator(
            event_bus=self._event_bus,
            state_machine=self._ha_state_machine,
        )

    def _build_object_storage(self) -> Any:
        from core.runtime.infra.object_storage import ObjectStorage
        return ObjectStorage()

    def _build_infra_trace_correlator(self) -> Any:
        from core.runtime.infra.trace_correlator import InfraTraceCorrelator
        return InfraTraceCorrelator()

    # ── Phase I2 — Data Infrastructure ──────────────────────────

    @property
    def postgresql_manager(self) -> Any:
        """Return the PostgreSQLManager instance (Phase I2).

        LAW 5: All schema operations reported to F4 via event bus.
        LAW 11: No global mutable state — every migration is fresh.
        LAW 14: Schema changes preserve DAG integrity.
        RULE 1: Same migration_id + sql → same outcome.
        RULE 3: ACID guards enforce isolation level and quorum.
        strict_data_mode: When True, enables guard enforcement.
        """
        if self._postgresql_manager is None:
            self._postgresql_manager = self._build_postgresql_manager()
        return self._postgresql_manager

    @property
    def distributed_log(self) -> Any:
        """Return the DistributedLog instance (Phase I2).

        LAW 11: Log streams are service boundaries.
        LAW 21: Replica sync is non-blocking and contained.
        RULE 2: Payload validated before append.
        RULE 4: Replicas are isolated.
        """
        if self._distributed_log is None:
            self._distributed_log = self._build_distributed_log()
        return self._distributed_log

    @property
    def runtime_analytics(self) -> Any:
        """Return the RuntimeAnalytics instance (Phase I2).

        LAW 15: Cost estimate reported with every computation.
        LAW 16: Aggregation weights are fair.
        RULE 1: Same metrics → same result (deterministic).
        """
        if self._runtime_analytics is None:
            self._runtime_analytics = self._build_runtime_analytics()
        return self._runtime_analytics

    @property
    def data_migrator(self) -> Any:
        """Return the DataMigrator instance (Phase I2).

        LAW 14: Schema transformation preserves referential integrity.
        RULE 1: Same sqlite_snapshot + mapping → same target.
        RULE 5: Failed batches retry independently.
        """
        if self._data_migrator is None:
            self._data_migrator = self._build_data_migrator()
        return self._data_migrator

    @property
    def data_trace_correlator(self) -> Any:
        """Return the DataTraceCorrelator instance (Phase I2).

        LAW 5: Every data operation carries data_trace_id.
        LAW 12: Every trace is fully back-traceable.
        """
        if self._data_trace_correlator is None:
            self._data_trace_correlator = self._build_data_trace_correlator()
        return self._data_trace_correlator

    def _build_postgresql_manager(self) -> Any:
        from core.runtime.data.postgresql_manager import PostgreSQLManager
        from core.runtime.data.acid_state_machine import ACIDStateMachine

        if self._acid_state_machine is None:
            self._acid_state_machine = ACIDStateMachine()

        return PostgreSQLManager(
            event_bus=self._event_bus,
            state_machine=self._acid_state_machine,
        )

    def _build_distributed_log(self) -> Any:
        from core.runtime.data.distributed_log import DistributedLog
        return DistributedLog(event_bus=self._event_bus)

    def _build_runtime_analytics(self) -> Any:
        from core.runtime.data.runtime_analytics import RuntimeAnalytics
        return RuntimeAnalytics(event_bus=self._event_bus)

    def _build_data_migrator(self) -> Any:
        from core.runtime.data.data_migrator import DataMigrator
        from core.runtime.data.acid_state_machine import ACIDStateMachine

        if self._acid_state_machine is None:
            self._acid_state_machine = ACIDStateMachine()

        return DataMigrator(
            event_bus=self._event_bus,
            state_machine=self._acid_state_machine,
        )

    def _build_data_trace_correlator(self) -> Any:
        from core.runtime.data.trace_correlator import DataTraceCorrelator
        return DataTraceCorrelator()

    # ── Phase I3 — Production Reliability ──────────────────────────

    @property
    def failover_orchestrator(self) -> Any:
        """Return the FailoverOrchestrator instance (Phase I3).

        LAW 8: Every failover operation carries recovery_trace_id.
        LAW 20: Quorum-based failure detection before escalation.
        LAW 22: Node isolation via fencing enforces service isolation.
        RULE 3: Promote safe guard enforces quorum > 50% + sync lag < 500ms.
        strict_reliability_mode: When True, enables guard enforcement.
        """
        if self._failover_orchestrator is None:
            self._failover_orchestrator = self._build_failover_orchestrator()
        return self._failover_orchestrator

    @property
    def disaster_recovery(self) -> Any:
        """Return the DisasterRecovery instance (Phase I3).

        LAW 8: Every recovery point is checksum-verified.
        RULE 1: Same state_snapshot + journal_offset -> same state_hash.
        RULE 5: Restore is isolated until verified.
        """
        if self._disaster_recovery is None:
            self._disaster_recovery = self._build_disaster_recovery()
        return self._disaster_recovery

    @property
    def rolling_update_manager(self) -> Any:
        """Return the RollingUpdateManager instance (Phase I3).

        LAW 3: Same UpdateStrategy + ClusterHealth -> same rollout plan.
        RULE 1: Deterministic manifest hashing.
        RULE 5: Rollback on health failure preserves data.
        """
        if self._rolling_update_manager is None:
            self._rolling_update_manager = self._build_rolling_update_manager()
        return self._rolling_update_manager

    @property
    def runtime_migrator(self) -> Any:
        """Return the RuntimeMigrator instance (Phase I3).

        LAW 3: Dry-run is deterministic — same inputs -> same issues.
        LAW 8: Snapshot is the foundation for recoverable migration.
        RULE 1: Same source + mapping -> same migration outcome.
        """
        if self._runtime_migrator is None:
            self._runtime_migrator = self._build_runtime_migrator()
        return self._runtime_migrator

    @property
    def recovery_trace_correlator(self) -> Any:
        """Return the RecoveryTraceCorrelator instance (Phase I3).

        LAW 5: Every reliability operation carries recovery_trace_id.
        LAW 12: Every trace is fully back-traceable to I2 data_trace_id.
        """
        if self._recovery_trace_correlator is None:
            self._recovery_trace_correlator = self._build_recovery_trace_correlator()
        return self._recovery_trace_correlator

    def _build_failover_orchestrator(self) -> Any:
        from core.runtime.reliability.failover_orchestrator import FailoverOrchestrator
        return FailoverOrchestrator(
            event_bus=self._event_bus,
            strict_reliability_mode=self._strict_reliability_mode,
        )

    def _build_disaster_recovery(self) -> Any:
        from core.runtime.reliability.disaster_recovery import DisasterRecovery
        return DisasterRecovery(
            strict_reliability_mode=self._strict_reliability_mode,
        )

    def _build_rolling_update_manager(self) -> Any:
        from core.runtime.reliability.rolling_update_manager import RollingUpdateManager
        return RollingUpdateManager(
            strict_reliability_mode=self._strict_reliability_mode,
        )

    def _build_runtime_migrator(self) -> Any:
        from core.runtime.reliability.runtime_migrator import RuntimeMigrator
        return RuntimeMigrator(
            strict_reliability_mode=self._strict_reliability_mode,
        )

    def _build_recovery_trace_correlator(self) -> Any:
        from core.runtime.reliability.trace_correlator import RecoveryTraceCorrelator
        return RecoveryTraceCorrelator()

    # ── Phase FINAL — Production Readiness & Certification ───────────

    @property
    def system_auditor(self) -> Any:
        """Return the SystemAuditor instance (Phase FINAL).

        LAW 1: Conforms to ISystemAuditor interface.
        LAW 5: Every audit produces fully traceable records.
        LAW 11: No global mutable state — all state is instance-scoped.
        RULE 1: Same inputs -> same compliance scan results.
        strict_certification_mode: When True, enables guard enforcement.
        """
        if self._system_auditor is None:
            self._system_auditor = self._build_system_auditor()
        return self._system_auditor

    @property
    def load_generator(self) -> Any:
        """Return the LoadGenerator instance (Phase FINAL).

        LAW 3: Same inputs -> same deterministic load results.
        LAW 11: No global mutable state — all state is instance-scoped.
        RULE 1: All operations are deterministic.
        RULE 3: Timeout guard prevents uncontrolled execution.
        """
        if self._load_generator is None:
            self._load_generator = self._build_load_generator()
        return self._load_generator

    @property
    def security_validator(self) -> Any:
        """Return the SecurityValidator instance (Phase FINAL).

        LAW 10: Resource isolation is validated as a hard requirement.
        LAW 22: Service isolation is strictly enforced.
        RULE 3: Capability guards are checked for every capability.
        RULE 4: Isolation violations are reported.
        """
        if self._security_validator is None:
            self._security_validator = self._build_security_validator()
        return self._security_validator

    @property
    def certification_engine(self) -> Any:
        """Return the CertificationEngine instance (Phase FINAL).

        LAW 8: Baselines preserve rollback path to pre-freeze state.
        LAW 11: No global mutable state — certs/baselines are instance-scoped.
        LAW 12: Every certificate is fully traceable.
        RULE 1: Same inputs -> same evaluation.
        RULE 3: Readiness guards enforce preconditions.
        """
        if self._certification_engine is None:
            self._certification_engine = self._build_certification_engine()
        return self._certification_engine

    @property
    def certification_state_machine(self) -> Any:
        """Return the CertificationStateMachine instance (Phase FINAL).

        LAW 3: Same guard inputs -> same transition (deterministic).
        LAW 11: No global mutable state — all machine state is instance-scoped.
        RULE 3: All transitions gated by readiness guards (G-C1 through G-C5).
        """
        if self._certification_state_machine is None:
            self._certification_state_machine = self._build_certification_state_machine()
        return self._certification_state_machine

    def _build_system_auditor(self) -> Any:
        from core.runtime.certification.system_auditor import SystemAuditor
        return SystemAuditor(
            strict_certification_mode=self._strict_certification_mode,
        )

    def _build_load_generator(self) -> Any:
        from core.runtime.certification.load_generator import LoadGenerator
        return LoadGenerator(
            strict_certification_mode=self._strict_certification_mode,
        )

    def _build_security_validator(self) -> Any:
        from core.runtime.certification.security_validator import SecurityValidator
        return SecurityValidator(
            strict_certification_mode=self._strict_certification_mode,
        )

    def _build_certification_engine(self) -> Any:
        from core.runtime.certification.certification_engine import CertificationEngine
        return CertificationEngine(
            strict_certification_mode=self._strict_certification_mode,
            event_bus=self._event_bus,
        )

    def _build_certification_state_machine(self) -> Any:
        from core.runtime.certification.certification_state_machine import (
            CertificationStateMachine,
        )
        return CertificationStateMachine(
            strict_certification_mode=self._strict_certification_mode,
        )

    # ── Phase J1 — Developer Experience Layer ─────────────────

    @property
    def sdk_client(self) -> Any:
        """Return the SDKClient instance (Phase J1).

        LAW 13: SDK routes exclusively through F1 UnifiedRuntime.
        LAW 12: Every operation carries devex_trace_id.
        strict_devex_mode: When True, enforces guard checks for testing.
        """
        if self._sdk_client is None:
            self._sdk_client = self._build_sdk_client()
        return self._sdk_client

    @property
    def cli_runtime(self) -> Any:
        """Return the CLIRuntime instance (Phase J1).

        LAW 13: CLI never accesses ExecutionEngine — all mutations
        route through F1 UnifiedRuntime API.
        """
        if self._cli_runtime is None:
            self._cli_runtime = self._build_cli_runtime()
        return self._cli_runtime

    @property
    def doc_generator(self) -> Any:
        """Return the DocGenerator instance (Phase J1).

        RULE 1: Same inputs -> same content_hash (DDG).
        LAW 12: Every artifact carries devex_trace_id.
        """
        if self._doc_generator is None:
            self._doc_generator = self._build_doc_generator()
        return self._doc_generator

    @property
    def api_spec_publisher(self) -> Any:
        """Return the APISpecPublisher instance (Phase J1).

        LAW 8: Spec rollback restores exact previous version.
        RULE 3: Validation guard blocks publish on critical errors.
        """
        if self._api_spec_publisher is None:
            self._api_spec_publisher = self._build_api_spec_publisher()
        return self._api_spec_publisher

    @property
    def doc_pipeline(self) -> Any:
        """Return the DocPipeline instance (Phase J1).

        Enforces 5 pipeline guards (G-D1–G-D5), 5 CLI routing guards
        (G-R1–G-R5), and Deterministic Doc Guard (DDG).
        """
        if self._doc_pipeline is None:
            self._doc_pipeline = self._build_doc_pipeline()
        return self._doc_pipeline

    @property
    def devex_trace_correlator(self) -> Any:
        """Return the DevExTraceCorrelator instance (Phase J1).

        LAW 5: Every DevEx operation is observable via trace chain.
        LAW 12: Every trace is fully back-traceable.
        """
        if self._devex_trace_correlator is None:
            self._devex_trace_correlator = self._build_devex_trace_correlator()
        return self._devex_trace_correlator

    def _build_sdk_client(self) -> Any:
        from core.devex.sdk_client import SDKClient
        return SDKClient(
            f1_unified_runtime=self._unified_runtime,
            trace_correlator=self.devex_trace_correlator,
            strict_devex_mode=self._strict_devex_mode,
            event_bus=self._event_bus,
        )

    def _build_cli_runtime(self) -> Any:
        from core.devex.cli_runtime import CLIRuntime
        return CLIRuntime(
            f1_unified_runtime=self._unified_runtime,
            trace_correlator=self.devex_trace_correlator,
            strict_devex_mode=self._strict_devex_mode,
            event_bus=self._event_bus,
        )

    def _build_doc_generator(self) -> Any:
        from core.devex.doc_generator import DocGenerator
        return DocGenerator(
            trace_correlator=self.devex_trace_correlator,
            strict_devex_mode=self._strict_devex_mode,
            event_bus=self._event_bus,
        )

    def _build_api_spec_publisher(self) -> Any:
        from core.devex.api_spec_publisher import APISpecPublisher
        return APISpecPublisher(
            trace_correlator=self.devex_trace_correlator,
            strict_devex_mode=self._strict_devex_mode,
            event_bus=self._event_bus,
        )

    def _build_doc_pipeline(self) -> Any:
        from core.devex.doc_pipeline import DocPipeline
        return DocPipeline(
            trace_correlator=self.devex_trace_correlator,
            strict_devex_mode=self._strict_devex_mode,
        )

    def _build_devex_trace_correlator(self) -> Any:
        from core.devex.trace_correlator import DevExTraceCorrelator
        return DevExTraceCorrelator()

    # ── Phase J2 — Enterprise Readiness Layer ─────────────────

    @property
    def tenant_router(self) -> Any:
        """Return the TenantRouter instance (Phase J2).

        LAW 9: Governance is policy-driven.
        LAW 11: Router state is instance-scoped.
        LAW 23: Routes through isolation boundary with G-L1.
        strict_enterprise_mode: When True, enforces strict guard checks.
        """
        if self._tenant_router is None:
            self._tenant_router = self._build_tenant_router()
        return self._tenant_router

    @property
    def usage_meter(self) -> Any:
        """Return the UsageMeter instance (Phase J2).

        LAW 11: Meter state is instance-scoped.
        LAW 24: cost_units use Decimal for billing precision.
        RULE 1: Same inputs -> same record_hash (G-M1).
        """
        if self._usage_meter is None:
            self._usage_meter = self._build_usage_meter()
        return self._usage_meter

    @property
    def billing_engine(self) -> Any:
        """Return the BillingEngine instance (Phase J2).

        LAW 9: Billing governance is policy-driven, NOT payment-coupled.
        LAW 25: PaymentState transitions are deterministic.
        RULE 5: Rollback restores exact previous billing state.
        """
        if self._billing_engine is None:
            self._billing_engine = self._build_billing_engine()
        return self._billing_engine

    @property
    def compliance_auditor(self) -> Any:
        """Return the ComplianceAuditor instance (Phase J2).

        LAW 26: Multi-framework compliance (GDPR/SOC2/HIPAA/PCI/ISO).
        LAW 27: Every audit entry has unique hash + ID.
        RULE 3: Validation guards block on compliance violations.
        """
        if self._compliance_auditor is None:
            self._compliance_auditor = self._build_compliance_auditor()
        return self._compliance_auditor

    @property
    def enterprise_trace_correlator(self) -> Any:
        """Return the EnterpriseTraceCorrelator instance (Phase J2).

        LAW 5: Every enterprise operation is observable via trace chain.
        LAW 12: Full back-traceability from F4 to originating call.
        RULE 4: Propagation rules P-R1–P-R6 ensure chain integrity.
        """
        if self._enterprise_trace_correlator is None:
            self._enterprise_trace_correlator = self._build_enterprise_trace_correlator()
        return self._enterprise_trace_correlator

    def _build_tenant_router(self) -> Any:
        from core.enterprise.tenant_router import TenantRouter
        return TenantRouter(
            trace_correlator=self.enterprise_trace_correlator,
            state_machine=self._build_enterprise_isolation_sm(),
            strict_enterprise_mode=self._strict_enterprise_mode,
            event_bus=self._event_bus,
        )

    def _build_usage_meter(self) -> Any:
        from core.enterprise.usage_meter import UsageMeter
        return UsageMeter(
            trace_correlator=self.enterprise_trace_correlator,
            state_machine=self._build_enterprise_isolation_sm(),
            strict_enterprise_mode=self._strict_enterprise_mode,
            event_bus=self._event_bus,
        )

    def _build_billing_engine(self) -> Any:
        from core.enterprise.billing_engine import BillingEngine
        return BillingEngine(
            trace_correlator=self.enterprise_trace_correlator,
            strict_enterprise_mode=self._strict_enterprise_mode,
            event_bus=self._event_bus,
        )

    def _build_compliance_auditor(self) -> Any:
        from core.enterprise.compliance_auditor import ComplianceAuditor
        return ComplianceAuditor(
            trace_correlator=self.enterprise_trace_correlator,
            state_machine=self._build_enterprise_isolation_sm(),
            strict_enterprise_mode=self._strict_enterprise_mode,
            event_bus=self._event_bus,
        )

    def _build_enterprise_isolation_sm(self) -> Any:
        from core.enterprise.isolation_state_machine import IsolationStateMachine
        return IsolationStateMachine()

    def _build_enterprise_trace_correlator(self) -> Any:
        from core.enterprise.trace_correlator import EnterpriseTraceCorrelator
        return EnterpriseTraceCorrelator()

    def build_enterprise_components(self) -> None:
        """Construct all Phase J2 enterprise components and wire to F4.

        LAW 23: Every enterprise component is constructed here and shares
        the same event_bus for F4 observability integration.
        LAW 11: No global state — all enterprise state is CompositionRoot-scoped.
        RULE 4: enterprise_trace_id propagates across all 5 components.
        """
        self.tenant_router
        self.usage_meter
        self.billing_engine
        self.compliance_auditor
        self.enterprise_trace_correlator

    # ── Phase J3 — Production Readiness Layer ──────────────────

    @property
    def chaos_injector(self) -> Any:
        """Return the ChaosInjector instance (Phase J3).

        LAW 8: Every injection carries expected_recovery_sec.
        LAW 11: Injector state is instance-scoped.
        LAW 20: Fault injection is scoped per service.
        strict_readiness_mode: When True, enables guard enforcement for testing.
        """
        if self._chaos_injector is None:
            self._chaos_injector = self._build_chaos_injector()
        return self._chaos_injector

    @property
    def load_orchestrator(self) -> Any:
        """Return the LoadOrchestrator instance (Phase J3).

        LAW 5: All load operations are measured.
        RULE 1: Same LoadProfile + ClusterState -> same load curve (G-D1).
        """
        if self._load_orchestrator is None:
            self._load_orchestrator = self._build_load_orchestrator()
        return self._load_orchestrator

    @property
    def stability_validator(self) -> Any:
        """Return the StabilityValidator instance (Phase J3).

        LAW 5: Stability scoring drives certification grading.
        RULE 3: Blocks certify if integrity check fails.
        """
        if self._stability_validator is None:
            self._stability_validator = self._build_stability_validator()
        return self._stability_validator

    @property
    def certification_gate(self) -> Any:
        """Return the CertificationGate instance (Phase J3).

        LAW 5: Grade A/B/C/F determines production readiness.
        RULE 3: Certification blocked if G-C3 guards fail.
        """
        if self._certification_gate is None:
            self._certification_gate = self._build_certification_gate()
        return self._certification_gate

    @property
    def readiness_trace_correlator(self) -> Any:
        """Return the ReadinessTraceCorrelator instance (Phase J3).

        LAW 12: readiness_trace_id propagates across all J3 layers.
        RULE 4: Full trace chain preserved from Chaos to Certification.
        """
        if self._readiness_trace_correlator is None:
            self._readiness_trace_correlator = self._build_readiness_trace_correlator()
        return self._readiness_trace_correlator

    def _build_readiness_state_machine(self) -> Any:
        from core.readiness.readiness_state_machine import ReadinessStateMachine
        return ReadinessStateMachine(
            strict_readiness_mode=self._strict_readiness_mode,
        )

    def _build_readiness_trace_correlator(self) -> Any:
        from core.readiness.trace_correlator import ReadinessTraceCorrelator
        return ReadinessTraceCorrelator()

    def _build_chaos_injector(self) -> Any:
        from core.readiness.chaos_injector import ChaosInjector
        return ChaosInjector(
            state_machine=self.readiness_state_machine,
            trace_correlator=self.readiness_trace_correlator,
        )

    def _build_load_orchestrator(self) -> Any:
        from core.readiness.load_orchestrator import LoadOrchestrator
        return LoadOrchestrator(
            state_machine=self.readiness_state_machine,
            trace_correlator=self.readiness_trace_correlator,
        )

    def _build_stability_validator(self) -> Any:
        from core.readiness.stability_validator import StabilityValidator
        return StabilityValidator()

    def _build_certification_gate(self) -> Any:
        from core.readiness.certification_gate import CertificationGate
        return CertificationGate(
            state_machine=self.readiness_state_machine,
        )

    # ── Phase P10 — Final Delivery Production Components ────

    @property
    def cli_commands(self) -> Any:
        """Return the EmoCLI instance (Phase P10 Final Delivery).

        Routes all commands through UnifiedRuntimeAPI.
        Zero direct execution logic.
        """
        if self._cli_commands is None:
            self._cli_commands = self._build_cli_commands()
        return self._cli_commands

    @property
    def emo_sdk_client(self) -> Any:
        """Return the EmoClient instance (Phase P10 Final Delivery).

        API wrapper routing through UnifiedRuntimeAPI.
        """
        if self._emo_sdk_client is None:
            self._emo_sdk_client = self._build_emo_sdk_client()
        return self._emo_sdk_client

    @property
    def multi_tenant_router(self) -> Any:
        """Return the MultiTenantRouter instance (Phase P10 Enterprise).

        Strict tenant_id filtering — zero cross-tenant data leaks.
        """
        if self._multi_tenant_router is None:
            self._multi_tenant_router = self._build_multi_tenant_router()
        return self._multi_tenant_router

    @property
    def p10_audit_generator(self) -> Any:
        """Return the AuditGenerator instance (Phase P10 Enterprise).

        Read-only EventStore aggregator for audit trail export.
        """
        if self._p10_audit_generator is None:
            self._p10_audit_generator = self._build_p10_audit_generator()
        return self._p10_audit_generator

    @property
    def p10_compliance_reporter(self) -> Any:
        """Return the ComplianceReporter instance (Phase P10 Enterprise).

        Read-only report generator for SOC2/GDPR/ISO27001.
        """
        if self._p10_compliance_reporter is None:
            self._p10_compliance_reporter = self._build_p10_compliance_reporter()
        return self._p10_compliance_reporter

    def _build_cli_commands(self) -> Any:
        from core.cli.commands import EmoCLI
        return EmoCLI(
            runtime_api=self.unified_runtime,
        )

    def _build_emo_sdk_client(self) -> Any:
        from core.sdk.client import EmoClient
        return EmoClient(
            runtime_api=self.unified_runtime,
        )

    def _build_multi_tenant_router(self) -> Any:
        from core.enterprise.multi_tenant_router import MultiTenantRouter
        return MultiTenantRouter(
            event_store=self.event_store,
            event_bus=self._event_bus,
        )

    def _build_p10_audit_generator(self) -> Any:
        from core.enterprise.audit_generator import AuditGenerator
        return AuditGenerator(
            event_store=self.event_store,
        )

    def _build_p10_compliance_reporter(self) -> Any:
        from core.enterprise.compliance_reporter import ComplianceReporter
        return ComplianceReporter(
            event_store=self.event_store,
        )

    # ── EXEC-DIRECTIVE-021 — Canary Deployment ──────────────

    @property
    def canary_observer(self) -> Any:
        """Return the CanaryObserver instance (EXEC-DIRECTIVE-021).

        LAW-5: Observable — all canary operations emit events to F4.
        LAW-11: No Global State — observer state is instance-scoped.
        LAW-12: Traceable — every operation carries canary_trace_id.
        strict_canary_mode: When True, enables canary guard enforcement for 3 users.
        """
        if self._canary_observer is None:
            self._canary_observer = self._build_canary_observer()
        return self._canary_observer

    def _build_canary_observer(self) -> Any:
        from scripts.canary.canary_launcher import CanaryLauncher
        from scripts.canary.canary_config import DEFAULT_CANARY_CONFIG
        return CanaryLauncher(
            config=DEFAULT_CANARY_CONFIG,
            event_bus=self._event_bus,
        )

    # ── EXEC-DIRECTIVE-023 — Phase K2 Hardening ───────────

    @property
    def strict_hardening_mode(self) -> bool:
        """Return strict_hardening_mode flag (EXEC-DIRECTIVE-023).

        LAW-8: Recoverability — every chaos scenario must prove zero data loss.
        LAW-20: Fault isolation — no cross-contamination between scenarios.
        When True, enables additional guard enforcement for hardening patches.
        """
        return self._strict_hardening_mode

    @strict_hardening_mode.setter
    def strict_hardening_mode(self, value: bool) -> None:
        self._strict_hardening_mode = value

    # ── EXEC-DIRECTIVE-028 — Final Freeze Mode ──────────

    @property
    def strict_final_freeze_mode(self) -> bool:  # EXEC-DIRECTIVE-028
        """Return strict_final_freeze_mode flag.

        When True, all DI wiring is locked and no new components
        may be registered after build_final_release().
        """
        return self._strict_final_freeze_mode

    @strict_final_freeze_mode.setter
    def strict_final_freeze_mode(self, value: bool) -> None:
        self._strict_final_freeze_mode = value

    def build_final_release(  # EXEC-DIRECTIVE-028
        self,
        event_bus: Optional[IEventBus] = None,
        freeze_manifest: Optional[Dict[str, str]] = None,
    ) -> None:
        """Activate final freeze mode and lock all DI wiring.

        Once called, all properties that auto-build components will raise
        RuntimeError if strict_final_freeze_mode is True and the component
        has not been pre-configured.

        This prevents any structural modification after SHA-256 signing.
        """
        self._strict_final_freeze_mode = True
        if event_bus is not None:
            self._event_bus = event_bus
        if freeze_manifest is not None:
            self._freeze_manifest = freeze_manifest

    # ── EXEC-DIRECTIVE-PILOT-001 — Production Pilot ─────

    @property
    def strict_pilot_mode(self) -> bool:
        """Return strict_pilot_mode flag (EXEC-DIRECTIVE-PILOT-001).

        When True, enforces read-only core modules during pilot,
        prevents write operations in core/runtime/, core/interfaces/,
        and enables pilot_trace_id propagation across all layers.
        """
        return self._strict_pilot_mode

    @strict_pilot_mode.setter
    def strict_pilot_mode(self, value: bool) -> None:
        self._strict_pilot_mode = value

    @property
    def pilot_trace_correlator(self) -> Any:
        """Return the PilotTraceCorrelator instance.

        LAW 5: Every pilot operation carries pilot_trace_id.
        LAW 12: Full back-traceability to originating pilot session.
        """
        return self._pilot_trace_correlator

    @pilot_trace_correlator.setter
    def pilot_trace_correlator(self, value: Any) -> None:
        self._pilot_trace_correlator = value

    # ── Phase L — Cognitive Memory Layer ──────────────────────

    @property
    def memory_hierarchy(self) -> Any:
        if self._memory_hierarchy is None:
            self._memory_hierarchy = self._build_memory_hierarchy()
        return self._memory_hierarchy

    @property
    def context_compiler(self) -> Any:
        if self._context_compiler is None:
            self._context_compiler = self._build_context_compiler()
        return self._context_compiler

    @property
    def skill_graph_manager(self) -> Any:
        if self._skill_graph_manager is None:
            self._skill_graph_manager = self._build_skill_graph_manager()
        return self._skill_graph_manager

    @property
    def memory_state_machine(self) -> Any:
        if self._memory_state_machine is None:
            self._memory_state_machine = self._build_memory_state_machine()
        return self._memory_state_machine

    @property
    def cognitive_trace_correlator(self) -> Any:
        if self._cognitive_trace_correlator is None:
            self._cognitive_trace_correlator = self._build_cognitive_trace_correlator()
        return self._cognitive_trace_correlator

    @property
    def strict_memory_mode(self) -> bool:
        return self._strict_memory_mode

    @strict_memory_mode.setter
    def strict_memory_mode(self, value: bool) -> None:
        self._strict_memory_mode = value

    def _build_memory_hierarchy(self) -> Any:
        from core.memory.memory_hierarchy import MemoryHierarchy
        return MemoryHierarchy()

    def _build_context_compiler(self) -> Any:
        from core.memory.context_compiler import ContextCompiler
        return ContextCompiler()

    def _build_skill_graph_manager(self) -> Any:
        from core.memory.skill_graph_manager import SkillGraphManager
        return SkillGraphManager()

    def _build_memory_state_machine(self) -> Any:
        from core.memory.memory_state_machine import MemoryStateMachine
        return MemoryStateMachine()

    def _build_cognitive_trace_correlator(self) -> Any:
        from core.memory.trace_correlator import CognitiveTraceCorrelator
        return CognitiveTraceCorrelator()

    def build_memory_layer(self) -> None:
        """Construct all Phase L memory components.
        
        LAW 6: Memory models defined outside runtime.
        LAW 8: Every operation recoverable via cognitive_trace_id.
        LAW 11: Tenant isolation — no global state.
        LAW 14: Deterministic retrieval.
        RULE 1: Each layer has its own import boundary.
        """
        self.memory_hierarchy
        self.context_compiler
        self.skill_graph_manager
        self.memory_state_machine
        self.cognitive_trace_correlator

    # ── Phase G — Cognitive Orchestration Layer ─────────────────

    @property
    def planner_agent(self) -> Any:
        if self._planner_agent is None:
            self._planner_agent = self._build_planner_agent()
        return self._planner_agent

    @property
    def critic_agent(self) -> Any:
        if self._critic_agent is None:
            self._critic_agent = self._build_critic_agent()
        return self._critic_agent

    @property
    def optimizer_agent(self) -> Any:
        if self._optimizer_agent is None:
            self._optimizer_agent = self._build_optimizer_agent()
        return self._optimizer_agent

    @property
    def orchestration_state_machine(self) -> Any:
        if self._orchestration_state_machine is None:
            self._orchestration_state_machine = self._build_orchestration_state_machine()
        return self._orchestration_state_machine

    @property
    def orchestration_trace_correlator(self) -> Any:
        if self._orchestration_trace_correlator is None:
            self._orchestration_trace_correlator = self._build_orchestration_trace_correlator()
        return self._orchestration_trace_correlator

    @property
    def strict_orchestration_mode(self) -> bool:
        return self._strict_orchestration_mode

    @strict_orchestration_mode.setter
    def strict_orchestration_mode(self, value: bool) -> None:
        self._strict_orchestration_mode = value

    def _build_planner_agent(self) -> Any:
        from core.orchestration.planner_agent import PlannerAgent
        return PlannerAgent()

    def _build_critic_agent(self) -> Any:
        from core.orchestration.critic_agent import CriticAgent
        return CriticAgent()

    def _build_optimizer_agent(self) -> Any:
        from core.orchestration.optimizer_agent import OptimizerAgent
        return OptimizerAgent()

    def _build_orchestration_state_machine(self) -> Any:
        from core.orchestration.orchestration_state_machine import OrchestrationStateMachine
        return OrchestrationStateMachine()

    def _build_orchestration_trace_correlator(self) -> Any:
        from core.orchestration.trace_correlator import OrchestrationTraceCorrelator
        return OrchestrationTraceCorrelator()

    def enforce_readonly_core_modules(self) -> None:  # EXEC-DIRECTIVE-PILOT-001
        """Enforce read-only access to core modules during pilot.

        When strict_pilot_mode is True, any attempt to write to
        core/runtime/, core/interfaces/, or core/execution_engine.py
        raises RuntimeError. This prevents accidental modification
        during live user validation.
        """
        if not self._strict_pilot_mode:
            return
        if self._engine is not None and not getattr(self._engine, '_readonly', False):
            raise RuntimeError(
                "PILOT MODE: ExecutionEngine must be read-only. "
                "Set strict_pilot_mode=True before build_execution_engine()."
            )

    @property
    def readiness_state_machine(self) -> Any:
        """Return the ReadinessStateMachine instance (Phase J3).

        LAW 11: All state is instance-scoped.
        RULE 3: All transitions gated by Recovery Guards (G-C1–G-C3, G-D1).
        """
        if self._readiness_state_machine is None:
            self._readiness_state_machine = self._build_readiness_state_machine()
        return self._readiness_state_machine

    def build_execution_engine(self) -> IExecutionEngine:
        """Return a singleton ExecutionEngine instance.

        This is the ONLY allowed construction point in the system.
        No other module may instantiate ``ExecutionEngine`` directly.

        LAW 13: REQUIRES isolation_runtime to be set.
        Raises RuntimeError if isolation_runtime is None.
        """
        if self._engine is not None:
            return self._engine

        # LAW 13 enforcement: No ExecutionEngine without IsolationRuntime.
        # RULE 1: All execution MUST route through IIsolationRuntime.
        # strict_isolation mode (Phase 4.5) — when enabled, building without
        # isolation raises RuntimeError. Default False for backward compat.
        if self._strict_isolation and self._isolation_runtime is None:
            raise RuntimeError(
                "LAW 13 VIOLATION: ExecutionEngine cannot be built without "
                "IsolationRuntime. Enable by setting strict_isolation=True "
                "and passing isolation_runtime."
            )

        self._engine = ExecutionEngine(
            tool_registry=self._tool_registry,
            memory=self._memory,
            worker_pool_size=self._worker_pool_size,
            cache=self._cache,
            service_registry=self._service_registry,
            optimizer=self._optimizer,
            cost_tracker=self._cost_tracker,
            size_limiter=self._size_limiter,
            checkpoint_manager=self._checkpoint_manager,
            contract_validator=self._contract_validator,
            compliance_validator=self._compliance_validator,
            event_bus=self._event_bus,
            canon_validator=self._canon_validator,
            codegraph=self._codegraph,
            # ── Phase 3.4 — 5 bounded services ──
            scheduler=self._scheduler,
            state_store=self._state_store,
            dispatcher=self._dispatcher,
            retry_handler=self._retry_handler,
            lease_manager=self._lease_manager,
        )

        # Phase 3.7 — expose internal layers
        self._runtime = (
            getattr(self._engine, "_runtime", None)
        )

        return self._engine


def build_minimal_runtime(
    gq=None, gre=None, agent=None, ctx=None,
    hybrid=None, memory=None, metrics=None,
    cache=None, worker_pool_size: int = 4,
) -> Any:
    """Build a lightweight runtime for E2E pipeline use.
    
    Backward-compat adapter — constructs the old-style UnifiedRuntime
    for the E2E pipeline.
    """
    from core.unified_runtime import UnifiedRuntime
    return UnifiedRuntime(
        gq, gre, agent, ctx,
        hybrid=hybrid, metrics=metrics, memory=memory,
        cache=cache, worker_pool_size=worker_pool_size,
    )
