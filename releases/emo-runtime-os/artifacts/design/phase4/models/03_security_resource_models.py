"""Phase 4 — Security & Resource Models.

DESIGN ONLY — Dataclass and Enum definitions for the isolation layer.
These are the canonical data structures referenced by all protocols
in 02_isolation_protocols.py.

Each model maps to a §15.15b component:
  Capability          → 4.2 Capability Security Model
  SandboxContext      → 4.1 Sandbox System
  QuotaModel          → 4.4 Resource Governance
  IsolationState      → 4.5 Execution Flow State Machine
  CapabilityStatus    → 4.2 Validation Result
  SecurityPolicy      → 4.3 IO & Network Isolation

All fields enumerated per Canon LAW 23-27 (Service Ownership).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional


# ═════════════════════════════════════════════════════════════════════
# 4.2 — Capability Security Model
# ═════════════════════════════════════════════════════════════════════

class AccessMode(str, Enum):
    """Filesystem and tool access modes.

    Ref: DEVELOPER.md §15.15b §4.2 — Capability Security Model
    Ref: Canon LAW 23-27 (Service Ownership — Scheduler handles execution ordering)
    """
    NONE = "none"
    READ = "read"
    WRITE = "write"
    FULL = "full"


@dataclass
class Capability:
    """Permission set for a tool.

    Defines what a tool is allowed to do during execution.
    Every tool MUST have a registered capability (RULE 3).

    Fields:
        tool_name: Name of the tool this capability governs.
        network: Network access mode.
        filesystem: Filesystem access mode.
        subprocess: Whether subprocess execution is allowed.
        max_cpu: Maximum CPU seconds (0 = unlimited).
        max_memory: Maximum memory in bytes (0 = unlimited).
        timeout: Maximum wall-clock time in seconds.
        allowed_domains: Whitelist of network domains.
        allowed_paths: Whitelist of filesystem paths.

    Ref: DEVELOPER.md §15.15b §4.2
    Ref: Canon RULE 3 (Capability First)
    """
    tool_name: str = ""
    network: AccessMode = AccessMode.NONE
    filesystem: AccessMode = AccessMode.NONE
    subprocess: bool = False
    max_cpu: float = 10.0
    max_memory: int = 256 * 1024 * 1024  # 256 MB
    timeout: float = 30.0
    allowed_domains: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)


@dataclass
class CapabilityStatus:
    """Result of a capability validation check.

    Attributes:
        allowed: Whether the execution is permitted.
        capability: The resolved Capability if allowed.
        reason: Denial reason if not allowed.
        violations: List of specific violations.

    Ref: DEVELOPER.md §15.15b §4.2 — ICapabilityGuard.validate()
    """
    allowed: bool = False
    capability: Optional[Capability] = None
    reason: str = ""
    violations: List[str] = field(default_factory=list)


# ═════════════════════════════════════════════════════════════════════
# 4.1 — Sandbox Context & Resources
# ═════════════════════════════════════════════════════════════════════

class FilesystemMode(str, Enum):
    """Filesystem access level for sandboxed execution.

    Ref: DEVELOPER.md §15.15b §4.1 — SandboxContext
    """
    NONE = "none"
    READ_ONLY = "read_only"
    WRITE_TEMP = "write_temp"
    FULL = "full"


class NetworkMode(str, Enum):
    """Network access level for sandboxed execution.

    Ref: DEVELOPER.md §15.15b §4.1 — SandboxContext
    """
    BLOCKED = "blocked"
    ALLOW_LIST = "allow_list"
    FULL = "full"


@dataclass
class SandboxContext:
    """Execution environment descriptor with resource constraints.

    Default: minimal privileges (no network, no filesystem, 256 MB, 30s timeout).

    This is the bridge between Capability (what's allowed) and
    SandboxExecutor (how it's enforced).

    Fields:
        cpu_limit: Max CPU time in seconds (0 = unlimited).
        memory_limit: Max memory in bytes (0 = unlimited).
        timeout: Max wall-clock time in seconds.
        filesystem_mode: Filesystem access level.
        network_mode: Network access level.
        allowed_paths: Filesystem path whitelist.
        allowed_domains: Network domain whitelist.
        working_dir: Working directory for the sandbox process.
        environment: Environment variables injected into the sandbox.
        sandbox_id: Unique sandbox instance identifier.
        execution_id: Unique execution identifier (for kill/telemetry).

    Ref: DEVELOPER.md §15.15b §4.1
    Ref: Canon RULE 4 (Everything is Killable — via timeout + RLIMIT)
    """
    cpu_limit: float = 1.0
    memory_limit: int = 256 * 1024 * 1024
    timeout: float = 30.0
    filesystem_mode: FilesystemMode = FilesystemMode.NONE
    network_mode: NetworkMode = NetworkMode.BLOCKED
    allowed_paths: List[str] = field(default_factory=list)
    allowed_domains: List[str] = field(default_factory=list)
    working_dir: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    sandbox_id: str = ""
    execution_id: str = ""

    def is_network_allowed(self, domain: str) -> bool:
        """Check if a specific domain is allowed under the current network mode."""
        if self.network_mode == NetworkMode.FULL:
            return True
        if self.network_mode == NetworkMode.BLOCKED:
            return False
        return any(domain == d or domain.endswith(f".{d}") for d in self.allowed_domains)

    def is_path_allowed(self, path: str, write: bool = False) -> bool:
        """Check if a filesystem path is allowed under the current mode."""
        import os as _os
        if write and self.filesystem_mode == FilesystemMode.READ_ONLY:
            return False
        if self.filesystem_mode == FilesystemMode.FULL:
            return True
        if self.filesystem_mode == FilesystemMode.NONE:
            return False
        resolved = _os.path.abspath(path)
        for allowed in self.allowed_paths:
            if resolved.startswith(_os.path.abspath(allowed)):
                return True
        return False


@dataclass
class SandboxInfo:
    """Runtime information about an active sandbox.

    Ref: DEVELOPER.md §15.15b §4.1 — SandboxManager lifecycle
    """
    sandbox_id: str
    context: SandboxContext
    created_at: float = 0.0
    pid: Optional[int] = None
    state: str = "created"  # created → active → destroyed
    execution_count: int = 0


# ═════════════════════════════════════════════════════════════════════
# 4.4 — Resource Governance Models
# ═════════════════════════════════════════════════════════════════════

@dataclass
class QuotaModel:
    """Resource quotas at three levels of granularity.

    Three tiers:
      - per_execution: Quotas for a single run (e.g., 5 min CPU, 512 MB).
      - per_worker: Quotas for a worker process (e.g., 30 min CPU, 2 GB).
      - global: System-wide quotas (e.g., 100 MB/s IO, 1000 executions).

    Each tier has:
      - max_cpu: Maximum CPU seconds.
      - max_memory: Maximum memory bytes.
      - max_wall_time: Maximum wall-clock seconds.
      - max_io_bytes: Maximum IO bytes (read + write).
      - max_executions: Maximum concurrent executions.

    Ref: DEVELOPER.md §15.15b §4.4 — Resource Governance
    Ref: Canon LAW 10 (Workers are unreliable — must enforce bounds)
    """
    max_cpu: float = float("inf")
    max_memory: int = float("inf")  # type: ignore[assignment]
    max_wall_time: float = float("inf")
    max_io_bytes: int = float("inf")  # type: ignore[assignment]
    max_executions: int = float("inf")  # type: ignore[assignment]


@dataclass
class ResourceUsage:
    """Resource consumption record for a single execution.

    Used by ResourceTracker for telemetry and by QuotaManager
    for enforcement decisions.

    Ref: DEVELOPER.md §15.15b §4.4 — ResourceTracker
    """
    execution_id: str
    tool: str
    cpu_time: float = 0.0
    memory_bytes: int = 0
    wall_time: float = 0.0
    io_bytes: int = 0


class QuotaScope(str, Enum):
    """Scope at which a quota is enforced.

    Ref: DEVELOPER.md §15.15b §4.4 — QuotaManager
    """
    EXECUTION = "execution"
    WORKER = "worker"
    GLOBAL = "global"


# ═════════════════════════════════════════════════════════════════════
# 4.3 — IO & Network Isolation Models
# ═════════════════════════════════════════════════════════════════════

@dataclass
class IOPolicy:
    """Policy for a specific IO operation type.

    Ref: DEVELOPER.md §15.15b §4.3 — IOPolicyEngine
    Ref: Canon RULE 2 (No uncontrolled IO)
    """
    allowed: bool = True
    allowed_domains: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)
    max_size: int = 0
    rate_limit: float = 0.0


@dataclass
class SecurityPolicy:
    """Combined security policy for an execution.

    Aggregates capability, IO, and network policies into a single
    authorization decision.

    Ref: DEVELOPER.md §15.15b §4.2-4.3
    Ref: Canon LAW 23-27
    """
    capability: Optional[Capability] = None
    io_policies: Dict[str, IOPolicy] = field(default_factory=dict)
    allowed_domains: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)
    enforce_network: bool = True
    enforce_filesystem: bool = True


# ═════════════════════════════════════════════════════════════════════
# 4.5 — Isolation State Machine
# ═════════════════════════════════════════════════════════════════════

class IsolationState(Enum):
    """State machine for the 5-step RULE 3 execution flow.

    Transition rules:
      VALIDATED         → RESOURCE_CHECKED     (on capability pass)
      RESOURCE_CHECKED   → SANDBOX_CREATED      (on quota pass)
      SANDBOX_CREATED    → EXECUTING            (on sandbox spawn)
      EXECUTING          → TELEMETRY_ARCHIVED   (on completion/error)
      TELEMETRY_ARCHIVED → (terminal)

    Failure transitions (any state → FAILED):
      VALIDATED          → FAILED               (capability violation)
      RESOURCE_CHECKED   → FAILED               (quota exceeded)
      SANDBOX_CREATED    → FAILED               (sandbox error)
      EXECUTING          → FAILED               (runtime error)

    Kill transitions (any non-terminal → KILLED):
      Any except TELEMETRY_ARCHIVED → KILLED    (kill() call)

    Ref: DEVELOPER.md §15.15b §4.5
    Ref: Canon RULE 3 (Capability First)
    Ref: Canon RULE 4 (Everything is Killable)
    """
    PENDING = auto()
    VALIDATED = auto()
    RESOURCE_CHECKED = auto()
    SANDBOX_CREATED = auto()
    EXECUTING = auto()
    TELEMETRY_ARCHIVED = auto()
    FAILED = auto()
    KILLED = auto()
    TIMED_OUT = auto()


# ═════════════════════════════════════════════════════════════════════
# Execution Result & Failure Context
# ═════════════════════════════════════════════════════════════════════

@dataclass
class ExecutionResult:
    """Standardized execution result for all isolation paths.

    Ref: DEVELOPER.md §15.15b — Unified return format
    """
    status: str = "completed"  # completed, failed, blocked, cancelled, timed_out
    result: Any = None
    error: str = ""
    reason: str = ""
    tool: str = ""
    execution_id: str = ""
    elapsed: float = 0.0
    sandbox_id: str = ""
    state: IsolationState = IsolationState.PENDING
    telemetry: Optional[ResourceUsage] = None


@dataclass
class FailureContext:
    """Context captured when an isolation step fails.

    Used for FailurePropagation decisions (RETRY, KILL, RELEASE LEASE, NOTIFY).

    Ref: 04_execution_flow_and_states.md — Failure Propagation Matrix
    """
    step: str  # capabilities, resources, sandbox, execution, telemetry
    exception: Optional[Exception] = None
    state: Optional[IsolationState] = None
    execution_id: str = ""
    tool: str = ""
    message: str = ""
    can_retry: bool = False
    suggested_action: str = "KILL"  # RETRY, KILL, RELEASE_LEASE, NOTIFY
