"""Phase J1 — Developer Experience Layer Protocols.  # LAW-1 LAW-2 LAW-5 LAW-12 LAW-13 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Formal typing.Protocols for the EMO SDK Client, CLI Runtime, Documentation
Generator, and API Spec Publisher. Every operation enforces traceability
(LAW 12) through devex_trace_id, interface authority (LAW 2) through strict
protocol conformance, and runtime isolation (LAW 13) by routing exclusively
through the F1 UnifiedRuntime API.

Ref: Canon LAW 1 (Interface Authority — all protocols are typing.Protocol)
Ref: Canon LAW 2 (Interface Authority — every method returns typed contracts)
Ref: Canon LAW 5 (Observability — all operations publish events)
Ref: Canon LAW 12 (Traceability — every operation carries devex_trace_id)
Ref: Canon LAW 13 (No Direct Execution — SDK/CLI must NOT bypass F1 API)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: ROADMAP 🔟 FINAL DELIVERY STAGE — Developer Experience
Ref: DEVELOPER.md §15.2 (Runtime Architecture), §15.13 (AI-Native Runtime)
Ref: F1 UnifiedRuntimeAPI (core/runtime/api/unified_runtime_api.py)
Ref: Phase J1 Design — 03_doc_and_cli_pipeline.md, 04_integration_blueprint.md
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ISDKClient(Protocol):  # LAW-1 LAW-2 LAW-5 LAW-12 LAW-13 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5
    """Formal SDK client contract for the EMO AI Runtime.

    The SDK is the ONLY external entry point for programmatic interaction.
    It communicates exclusively with the F1 UnifiedRuntimeAPI — never
    directly with ExecutionEngine, D8 services, or I1/I2/I3 layers.

    Every public method requires devex_trace_id for full back-traceability
    (LAW 12). All state transitions are guarded (RULE 3). All IO is
    validated before submission (RULE 2).

    Ref: F1 UnifiedRuntimeAPI submit/resume/cancel/observe/replay
    Ref: DEVELOPER.md §15.2 (Runtime Architecture)
    Ref: Phase J1 — 04_integration_blueprint.md §2 (Flow Map)
    """

    async def connect(  # LAW-5 LAW-12 LAW-13 RULE-2
        self,
        endpoint: str,
        auth_token: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Establish an authenticated connection to the Runtime endpoint.

        Args:
            endpoint:        F1 UnifiedRuntime API endpoint URI (e.g., "https://runtime.emo.ai/v1").
            auth_token:      Authentication token for the Runtime endpoint.
            devex_trace_id:  Correlation ID for full traceability (LAW 12).

        Returns:
            connected:         True if the handshake succeeded.
            session_id:        Server-assigned session identifier.
            server_version:    Runtime version string.
            supported_apis:    List of supported API versions.
            endpoint_health:   Health status of the endpoint.
            trace_id:          Echoed devex_trace_id for correlation.

        LAW 13: SDK connects ONLY to F1 UnifiedRuntime — never to lower layers.
        LAW 5: Connection attempt MUST be observable via EventBus.
        RULE 2: endpoint and auth_token MUST be validated before handshake.
        """

    async def submit_dag(  # LAW-1 LAW-2 LAW-12 LAW-13 RULE-1 RULE-3
        self,
        dag_spec: Dict[str, Any],
        context: Dict[str, Any],
        options: Dict[str, Any],
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Submit a DAG for execution through the F1 UnifiedRuntime API.

        Delegates directly to F1 UnifiedRuntime.submit(). The SDK MUST NOT
        interact with ExecutionEngine, IIsolationRuntime, or any D8 service.

        Args:
            dag_spec:         DAG specification conforming to F1 DAG schema.
            context:          Execution context (tenant_id, priority, tags).
            options:          Execution options (timeout_sec, max_retries).
            devex_trace_id:   Correlation ID for traceability (LAW 12).

        Returns:
            ticket_id:         F1-assigned execution ticket.
            status:            Initial execution status ("submitted").
            trace_id:          Echoed devex_trace_id.
            submitted_at_ns:   Submission timestamp.
            estimated_cost:    Estimated cost units for execution.

        LAW 1: DAG spec MUST conform to ISubmittableDAG interface.
        LAW 13: SDK MUST route through F1 UnifiedRuntime — NO direct execution.
        RULE 1: Same dag_spec + context -> same submission result.
        RULE 3: Submission guard pre-checks isolation_runtime.
        """

    async def observe_execution(  # LAW-5 LAW-12 RULE-2
        self,
        ticket_id: str,
        devex_trace_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream execution state changes for a submitted DAG.

        Delegates to F1 UnifiedRuntime.observe(). Returns an async iterator
        of live state snapshots until the DAG completes or is cancelled.

        Args:
            ticket_id:        F1 execution ticket to observe.
            devex_trace_id:   Correlation ID.

        Yields:
            state:            Current execution state ("running", "completed", "failed").
            node_statuses:    Per-node execution status.
            progress_pct:     Overall execution progress (0.0–100.0).
            timestamp_ns:     State observation timestamp.
            trace_id:         Echoed devex_trace_id.

        LAW 5: Every observation is observable via EventBus.
        LAW 12: Every yield carries devex_trace_id.
        RULE 2: Observation is read-only — no mutation.
        """

    async def disconnect(  # LAW-5 RULE-2
        self,
        session_id: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Gracefully disconnect from the Runtime endpoint.

        Args:
            session_id:      Active session identifier.
            devex_trace_id:  Correlation ID.

        Returns:
            disconnected:    True if the session was cleanly terminated.
            session_duration_sec: Duration of the session.
            remaining_leases: Number of leases still held.
            trace_id:        Echoed devex_trace_id.

        LAW 5: Disconnection MUST be observable.
        RULE 2: No uncontrolled IO — clean teardown only.
        """


@runtime_checkable
class ICLIRuntime(Protocol):  # LAW-5 LAW-12 LAW-13 RULE-1 RULE-2 RULE-3 RULE-4
    """CLI runtime contract for admin and debug operations.

    The CLI provides human-facing commands that read from the Runtime or
    CodeGraph. CLI commands MUST NEVER write directly to ExecutionEngine
    or D8 services — all mutations route through F1 UnifiedRuntime API.

    Ref: F1 UnifiedRuntimeAPI (observe, replay, cancel)
    Ref: CodeGraph v1 read-only queries
    Ref: Phase J1 — 03_doc_and_cli_pipeline.md §Routing Guards
    """

    async def status(  # LAW-5 LAW-13 RULE-2
        self,
        runtime_uri: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Query the Runtime health and status.

        Args:
            runtime_uri:     Runtime endpoint URI for health check.
            devex_trace_id:  Correlation ID.

        Returns:
            runtime_healthy:    True if runtime is reachable and healthy.
            version:            Runtime version.
            uptime_sec:         Uptime in seconds.
            active_tickets:     Number of active execution tickets.
            worker_count:       Registered worker count.
            queue_depth:        Current execution queue depth.
            trace_id:           Echoed devex_trace_id.

        LAW 5: Status query MUST be observable.
        LAW 13: Status is READ-ONLY — no mutation of runtime state.
        RULE 2: Read-only query — no IO side effects.
        """

    async def logs(  # LAW-5 LAW-12 RULE-2
        self,
        trace_id: str,
        tail: int,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Fetch logs for a given trace_id.

        Args:
            trace_id:        Target trace ID to fetch logs for.
            tail:            Number of recent log lines to return.
            devex_trace_id:  Correlation ID for this CLI operation.

        Returns:
            log_entries:     List of log entry dicts.
            total_available: Total log lines available for this trace_id.
            trace_id:        Target trace_id.
            fetched_at_ns:   Fetch timestamp.

        LAW 5: Logs MUST be observable through the EventBus.
        LAW 12: Every log entry carries original trace_id.
        RULE 2: Read-only query — no mutation.
        """

    async def replay(  # LAW-8 LAW-12 LAW-13 RULE-1 RULE-5
        self,
        execution_id: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Replay a past execution for debugging/deterministic verification.

        Delegates to F1 UnifiedRuntime.replay(). CLI MUST NOT replay
        directly from the ExecutionEngine or IRecoveryCoordinator.

        Args:
            execution_id:    Execution identifier to replay.
            devex_trace_id:  Correlation ID.

        Returns:
            replay_id:       Replay ticket identifier.
            status:          Replay status.
            original_trace_id: Trace ID of the original execution.
            replayed_nodes:  Number of nodes replayed.
            duration_ms:     Replay duration.
            trace_id:        Echoed devex_trace_id.

        LAW 8: Replay must reproduce the exact execution sequence.
        LAW 13: Replay MUST route through F1 — never direct to IRecoveryCoordinator.
        RULE 1: Same execution_id -> same replay output.
        RULE 5: Replay is self-contained — no side effects on live state.
        """

    async def validate_architecture(  # LAW-1 LAW-2 RULE-1
        self,
        config_path: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Validate an architecture config against CodeGraph + Canon Laws.

        Read-only query against CodeGraph v1. Does NOT modify any runtime
        state. Returns compliance violations and suggestions.

        Args:
            config_path:     Path to architecture config file.
            devex_trace_id:  Correlation ID.

        Returns:
            valid:              True if config conforms to all laws.
            total_checks:       Number of validation checks performed.
            violations:         List of canon/rules violations found.
            suggestions:        List of architecture suggestions.
            codegraph_snapshot: CodeGraph version used for validation.
            trace_id:           Echoed devex_trace_id.

        LAW 1: Config MUST conform to IArchitectureConfig interface.
        LAW 2: Validation is against typed contracts only.
        RULE 1: Same config + same CodeGraph snapshot -> same validation.
        """


@runtime_checkable
class IDocGenerator(Protocol):  # LAW-1 LAW-2 LAW-5 LAW-12 RULE-1 RULE-2 RULE-3 RULE-4
    """Documentation generator contract for the DevEx Documentation Portal.

    Produces deterministic documentation artifacts from CodeGraph snapshots,
    Canon Laws, and F1 API specs. Every artifact carries a content_hash
    (SHA-256) for integrity verification (RULE 1).

    Ref: CodeGraph v1 static analysis structures
    Ref: Canon Laws 1-27, RULE 1-5
    Ref: F1 API Specs (IAPISpecPublisher)
    Ref: Phase J1 — 03_doc_and_cli_pipeline.md §Doc Pipeline
    """

    async def extract_codegraph_structure(  # LAW-1 LAW-2 RULE-1
        self,
        codegraph_snapshot: Dict[str, Any],
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Extract a structured representation from a CodeGraph snapshot.

        Args:
            codegraph_snapshot: Full CodeGraph snapshot dict.
            devex_trace_id:     Correlation ID.

        Returns:
            modules:           List of extracted module definitions.
            interfaces:        List of extracted interface definitions.
            dependencies:      Dependency graph between modules.
            component_count:   Total number of components.
            interface_count:   Total number of interfaces.
            version:           CodeGraph version used.

        LAW 1: All extracted interfaces MUST conform to IInterface definitions.
        RULE 1: Same snapshot -> same structure (deterministic extraction).
        RULE 2: Extraction is read-only — no mutation.
        """

    async def render_canon_laws(  # LAW-5 RULE-1
        self,
        canon_version: str,
        output_format: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Render Canon Laws and Rules into documentation format.

        Args:
            canon_version:   Canon version string to render.
            output_format:   "markdown", "html", or "json".
            devex_trace_id:  Correlation ID.

        Returns:
            artifact_id:       Unique artifact identifier.
            content:           Rendered content (format-dependent).
            format:            Output format.
            canon_version:     Canon version used.
            content_hash:      SHA-256 hash of rendered content.
            law_count:         Number of laws rendered.
            rule_count:        Number of rules rendered.

        LAW 5: Law rendering is observable.
        RULE 1: Same canon_version + output_format -> same rendered content.
        """

    async def generate_api_reference(  # LAW-1 LAW-2 LAW-12 RULE-1
        self,
        api_spec: Dict[str, Any],
        output_format: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Generate API reference documentation from a spec payload.

        Args:
            api_spec:        Complete API spec (OpenAPI/AsyncAPI compatible).
            output_format:   "openapi_json", "openapi_yaml", "markdown", "html".
            devex_trace_id:  Correlation ID.

        Returns:
            artifact_id:       Unique artifact identifier.
            content:           Generated reference content.
            format:            Output format.
            endpoint_count:    Number of documented endpoints.
            schema_count:      Number of documented schemas.
            content_hash:      SHA-256 hash of generated content.
            trace_id:          Echoed devex_trace_id.

        LAW 1: Generated reference MUST conform to IAPIDocEntry interface.
        RULE 1: Same api_spec + format -> same reference content.
        """

    async def publish_artifact(  # LAW-5 LAW-12 RULE-4
        self,
        artifact_id: str,
        target_repository: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Publish a generated documentation artifact to a target repository.

        Args:
            artifact_id:        Artifact identifier to publish.
            target_repository:  Target repository/path for publishing.
            devex_trace_id:     Correlation ID.

        Returns:
            published:         True if publication succeeded.
            artifact_id:       Published artifact identifier.
            target_repository: Target repository path.
            publish_url:       URL of the published artifact.
            published_at_ns:   Publication timestamp.
            trace_id:          Echoed devex_trace_id.

        LAW 5: Publication MUST be observable.
        LAW 12: Published artifacts carry original devex_trace_id.
        RULE 4: Publication is scoped — no cross-repository impact.
        """


@runtime_checkable
class IAPISpecPublisher(Protocol):  # LAW-1 LAW-2 LAW-5 LAW-12 RULE-1 RULE-2 RULE-3 RULE-4
    """API Spec publisher contract for automatic OpenAPI/AsyncAPI distribution.

    Loads Runtime spec definitions, validates OpenAPI schema conformance,
    publishes async event schemas, and supports rollback on validation
    failure.

    Ref: OpenAPI 3.1 Specification
    Ref: AsyncAPI 2.6 Specification
    Ref: F1 UnifiedRuntime API method signatures
    Ref: Phase J1 — 03_doc_and_cli_pipeline.md §Spec Pipeline
    """

    async def load_runtime_spec(  # LAW-1 LAW-2 RULE-2
        self,
        runtime_version: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Load the Runtime API spec definition for a given version.

        Args:
            runtime_version: Runtime version to load spec for.
            devex_trace_id:  Correlation ID.

        Returns:
            spec_id:           Unique spec identifier.
            runtime_version:   Runtime version.
            openapi_version:   OpenAPI version used.
            endpoint_count:    Number of API endpoints defined.
            schema_count:      Number of API schemas defined.
            spec_hash:         SHA-256 hash of the spec content.
            loaded_at_ns:      Load timestamp.

        LAW 1: Loaded spec MUST conform to IOpenAPISpec interface.
        RULE 2: Loading is read-only — no mutation of spec source.
        """

    async def validate_openapi_schema(  # LAW-1 LAW-2 RULE-1 RULE-3
        self,
        spec_payload: Dict[str, Any],
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Validate an OpenAPI spec payload against the OpenAPI 3.1 schema.

        Args:
            spec_payload:     Full OpenAPI spec payload to validate.
            devex_trace_id:  Correlation ID.

        Returns:
            valid:                True if the spec passes all validations.
            errors:               List of schema validation errors.
            warnings:             List of schema validation warnings.
            endpoint_count:       Number of endpoints validated.
            schema_count:         Number of schemas validated.
            validation_duration_ms: Validation duration.

        LAW 1: Spec MUST conform to IOpenAPISchema interface.
        RULE 1: Same spec_payload -> same validation result.
        RULE 3: Validation guard blocks publish on critical errors.
        """

    async def publish_async_events(  # LAW-5 RULE-4
        self,
        event_specs: Dict[str, Any],
        target_broker: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Publish AsyncAPI event schemas to a target message broker.

        Args:
            event_specs:      Dict of event_name -> AsyncAPI channel definition.
            target_broker:    Target broker URI for publishing.
            devex_trace_id:   Correlation ID.

        Returns:
            published:         True if all event schemas published.
            total_events:      Number of event schemas published.
            failed_events:     Number of event schemas that failed.
            broker:            Target broker URI.
            trace_id:          Echoed devex_trace_id.

        LAW 5: Publication MUST be observable via EventBus.
        RULE 4: Publication is scoped per broker — no cross-broker impact.
        """

    async def rollback_spec(  # LAW-8 RULE-5
        self,
        spec_id: str,
        previous_spec_hash: str,
        devex_trace_id: str,
    ) -> Dict[str, Any]:
        """Rollback a published spec to a previous version.

        Args:
            spec_id:            Spec identifier to rollback.
            previous_spec_hash: SHA-256 hash of the previous valid spec.
            devex_trace_id:     Correlation ID.

        Returns:
            rolled_back:        True if rollback succeeded.
            spec_id:            Spec identifier.
            previous_hash:      Previous spec hash restored.
            restored_endpoints: Number of endpoints restored.
            trace_id:           Echoed devex_trace_id.

        LAW 8: Rollback must restore the exact previous spec version.
        RULE 5: Rollback is self-contained — no side effects on live specs.
        """
