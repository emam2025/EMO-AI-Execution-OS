"""Phase J1 — SDK, CLI & Documentation Models.  # LAW-1 LAW-2 LAW-5 LAW-12 LAW-13 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Shared dataclasses and enums for all J1 components: ISDKClient, ICLIRuntime,
IDocGenerator, and IAPISpecPublisher. Every model carries devex_trace_id
for full back-traceability (LAW 12). All content hashes use SHA-256 for
deterministic verification (RULE 1).

Ref: Canon LAW 1 (Interface Authority), LAW 2 (Interface Contracts)
Ref: Canon LAW 5 (Observability), LAW 12 (Traceability), LAW 13 (No Direct Execution)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: ROADMAP 🔟 FINAL DELIVERY STAGE — Developer Experience
Ref: DEVELOPER.md §15.2 (Runtime Architecture), §15.13 (AI-Native Runtime)
Ref: F1 models (core/runtime/api/unified_runtime_api.py)
Ref: Phase J1 Design — 01_devex_protocols.py, 03_doc_and_cli_pipeline.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────


class SDKAuthMethod(str, Enum):  # LAW-2 LAW-12
    """Authentication methods supported by the SDK."""
    BEARER_TOKEN = "bearer_token"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    MUTUAL_TLS = "mutual_tls"


class CLIOutputFormat(str, Enum):  # LAW-5
    """Output formats for CLI commands."""
    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    TABLE = "table"


class DocArtifactType(str, Enum):  # LAW-1 LAW-2
    """Types of documentation artifacts."""
    MARKDOWN = "md"
    HTML = "html"
    JSON = "json"
    OPENAPI_JSON = "openapi_json"
    OPENAPI_YAML = "openapi_yaml"
    ASYNCAPI_JSON = "asyncapi_json"


class PublishStatus(str, Enum):  # LAW-5
    """Publication status for doc artifacts."""
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class SpecFormat(str, Enum):  # LAW-1
    """API specification format."""
    OPENAPI_3_1 = "openapi_3.1"
    ASYNCAPI_2_6 = "asyncapi_2.6"


class GuardDecision(str, Enum):  # LAW-13 RULE-3
    """Decision output from a routing guard check."""
    ALLOW = "allow"
    BLOCK = "block"
    FLAG = "flag"


class CLIAccessLevel(str, Enum):  # LAW-13
    """Access level for CLI commands relative to the Runtime."""
    READ_ONLY = "read_only"
    F1_PROXIED = "f1_proxied"
    CODEGRAPH_ONLY = "codegraph_only"


# ── SDK Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class SDKConfig:  # LAW-2 LAW-12 LAW-13
    """Configuration for an SDK client session.

    LAW 12: trace_injector ensures every API call carries devex_trace_id.
    LAW 13: SDKConfig endpoint MUST point to F1 UnifiedRuntime — never to
    ExecutionEngine, D8 services, or I-layer components directly.
    """
    endpoint: str
    auth_token: str
    trace_injector: str  # "auto" | "manual" | "propagate"
    retry_policy: str  # "exponential_backoff" | "linear" | "none"
    timeout_sec: float = 30.0
    max_retries: int = 3
    auth_method: SDKAuthMethod = SDKAuthMethod.BEARER_TOKEN
    tls_verify: bool = True
    additional_headers: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SDKConnectionResult:  # LAW-5 LAW-12
    """Result of an SDK connection handshake."""
    session_id: str
    server_version: str
    supported_apis: List[str]
    endpoint_health: str
    trace_id: str
    connected_at_ns: int = 0


@dataclass(frozen=True)
class DAGSubmissionRequest:  # LAW-1 LAW-2
    """Standardised DAG submission request payload.

    Conforms to F1 UnifiedRuntime.submit() dag_spec + context + options schema.
    """
    dag_spec: Dict[str, Any]
    context: Dict[str, Any]
    options: Dict[str, Any]
    devex_trace_id: str


@dataclass(frozen=True)
class DAGSubmissionResult:  # LAW-5 LAW-12
    """Result of a DAG submission through the SDK."""
    ticket_id: str
    status: str
    trace_id: str
    submitted_at_ns: int
    estimated_cost: float = 0.0


@dataclass(frozen=True)
class ExecutionObservation:  # LAW-5 LAW-12
    """A single observation frame from an active execution stream."""
    state: str
    node_statuses: Dict[str, str]
    progress_pct: float
    timestamp_ns: int
    trace_id: str


# ── CLI Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class CLICommandSpec:  # LAW-2 LAW-13
    """Specification for a single CLI command.

    LAW 13: 'requires_runtime' indicates whether the command needs a
    running Runtime. If True, the command MUST route through F1 API.
    'access_level' gates whether the command reads from CodeGraph
    (read-only) or mutates state (F1-proxied only).

    Ref: Phase J1 — 03_doc_and_cli_pipeline.md §Routing Guard Matrix
    """
    command_name: str
    subcommand: str
    flags: List[str]
    requires_runtime: bool
    output_format: CLIOutputFormat = CLIOutputFormat.TEXT
    access_level: CLIAccessLevel = CLIAccessLevel.READ_ONLY
    description: str = ""
    usage_example: str = ""


@dataclass(frozen=True)
class CLICommandResult:  # LAW-5 LAW-12
    """Result of executing a CLI command."""
    command: str
    subcommand: str
    success: bool
    data: Dict[str, Any]
    trace_id: str
    duration_ms: float = 0.0
    error: str = ""


@dataclass(frozen=True)
class CLIRoutingDecision:  # LAW-13 RULE-3
    """Routing decision produced by the CLI guard evaluator."""
    command: str
    target_layer: str  # "f1_unified_api" | "codegraph_read" | "blocked"
    decision: GuardDecision
    guard_checks: Dict[str, bool]
    reason: str = ""


# ── Documentation Models ─────────────────────────────────────


@dataclass(frozen=True)
class DocArtifact:  # LAW-1 LAW-5 LAW-12 RULE-1
    """A documentation artifact produced by IDocGenerator.

    LAW 12: Every artifact carries original devex_trace_id.
    RULE 1: content_hash ensures deterministic content verification.
    """
    artifact_id: str
    artifact_type: DocArtifactType
    source_module: str
    version: str
    content_hash: str
    publish_status: PublishStatus = PublishStatus.DRAFT
    trace_id: str = ""
    created_at_ns: int = 0
    size_bytes: int = 0


@dataclass(frozen=True)
class APISpecPayload:  # LAW-1 LAW-2 RULE-1
    """API specification payload for OpenAPI/AsyncAPI publication.

    LAW 1: Conforms to IOpenAPISpec / IAsyncAPISpec interfaces.
    RULE 1: Same server_endpoints + path_definitions + event_schemas -> same spec_hash.
    """
    openapi_version: str
    server_endpoints: List[Dict[str, Any]]
    path_definitions: Dict[str, Any]
    event_schemas: Dict[str, Any]
    compliance_tags: List[str]
    spec_hash: str = ""
    spec_format: SpecFormat = SpecFormat.OPENAPI_3_1
    description: str = ""

    def __post_init__(self) -> None:
        import hashlib
        if not self.spec_hash:
            raw = f"{self.openapi_version}:{self.server_endpoints}:{self.path_definitions}:{self.event_schemas}"
            object.__setattr__(self, "spec_hash", hashlib.sha256(raw.encode()).hexdigest())


@dataclass(frozen=True)
class DocGenerationRequest:  # LAW-5 LAW-12
    """Request to generate a documentation artifact."""
    source_type: str  # "codegraph", "canon", "api_spec", "architecture"
    source_ref: str
    output_format: str
    devex_trace_id: str
    include_private: bool = False
    version: str = "latest"


@dataclass(frozen=True)
class SpecPublicationReceipt:  # LAW-5 LAW-12
    """Receipt for a spec publication or rollback operation."""
    spec_id: str
    action: str  # "published" | "rolled_back"
    target: str
    success: bool
    trace_id: str
    published_at_ns: int = 0
    artifact_count: int = 0


# ── Trace Models ─────────────────────────────────────────────


@dataclass(frozen=True)
class DevExTraceContext:  # LAW-5 LAW-12
    """Trace context propagated through all DevEx operations.

    devex_trace_id is the correlation anchor that links SDK calls, CLI
    commands, doc generation, and spec publishing into a single trace
    chain. Every J1 protocol method accepts and returns devex_trace_id.

    Ref: Phase J1 — 04_integration_blueprint.md §Correlation ID Strategy
    """
    devex_trace_id: str
    origin_layer: str  # "sdk" | "cli" | "doc_generator" | "spec_publisher"
    parent_trace_id: str = ""
    session_id: str = ""
    user_id: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
