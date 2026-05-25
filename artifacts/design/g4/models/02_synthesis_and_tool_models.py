"""Phase G4 — Tool Synthesis Agent: Models.  # LAW-11 LAW-12 LAW-14 LAW-2 LAW-10

Shared dataclass / Enum definitions for the Tool Synthesis Agent subsystem.
Mirrors the canonical model definitions from ROADMAP Phase G4 and §15.15b.

All models carry synthesis_trace_id or ast_hash for LAW 12 and LAW 14 compliance.

Ref: Canon LAW 2 (Interface Authority), LAW 10 (Unreliable Workers)
Ref: Canon LAW 11 (No Global State), LAW 12 (Traceability)
Ref: Canon LAW 14 (Resource Governance), RULE 1-4
Ref: DEVELOPER.md §15.2, §15.10, §15.15b
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════


class SynthesisSignal(str, Enum):  # LAW-8
    """Discrete synthesis outcome signals.

    Maps to the Terminal / Escalation states of the Synthesis State Machine.
    """
    APPROVE = "approve"               # All guards passed → register
    REJECT_CODE = "reject_code"       # Code generation failed / invalid AST
    REJECT_SECURITY = "reject_security"  # Security scan failed
    REQUIRE_REVISION = "require_revision"  # Capability mismatch → re-synthesize
    ESCALATE = "escalate"             # Unresolvable → human-in-the-loop


class SynthesisState(str, Enum):  # LAW-14
    """All states of the Synthesis State Machine."""
    INTENT_RECEIVED = "intent_received"
    CODE_GENERATION = "code_generation"
    AST_VALIDATION = "ast_validation"
    SECURITY_SCAN = "security_scan"
    SANDBOX_DRY_RUN = "sandbox_dry_run"
    REGISTER = "register"
    REJECT = "reject"
    ESCALATE = "escalate"


class ValidationSeverity(str, Enum):  # RULE-2
    """Severity levels for security findings."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NetworkMode(str, Enum):  # RULE-2 RULE-4
    """Network access mode for sandbox execution."""
    BLOCKED = "blocked"
    ISOLATED = "isolated"  # Loopback only


class RegistrationStatus(str, Enum):  # LAW-2 LAW-14
    """Status of a tool registration attempt."""
    REGISTERED = "registered"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    PENDING = "pending"


# ═══════════════════════════════════════════════════════════════════
# Synthesis-level models
# ═══════════════════════════════════════════════════════════════════


@dataclass
class SynthesizedTool:  # LAW-12 LAW-14
    """Complete record of a synthesised tool, from intent to registration.

    All fields are populated across the synthesis pipeline stages.
    synthesis_trace_id (LAW 12) and ast_hash (LAW 14) are mandatory.
    """
    tool_id: str = ""
    synthesis_trace_id: str = ""  # LAW 12
    plan_id: str = ""
    intent_id: str = ""

    # Code generation
    generated_code: str = ""
    ast_hash: str = ""            # LAW 14 — SHA-256 of canonical AST

    # Capability & risk
    capability_set: List[str] = field(default_factory=list)
    estimated_risk_score: float = 0.0

    # Validation results
    ast_valid: bool = False
    no_os_imports: bool = False
    capability_match_score: float = 0.0
    security_findings: List[Dict[str, Any]] = field(default_factory=list)

    # Sandbox results
    sandbox_test_results: Dict[str, Any] = field(default_factory=dict)

    # Registration
    registration_status: RegistrationStatus = RegistrationStatus.PENDING
    registration_id: str = ""
    rollback_token: str = ""
    compliance_proof: Dict[str, Any] = field(default_factory=dict)

    # Trace chain
    g1_planner_trace_id: str = ""
    g3_optimizer_trace_id: str = ""


@dataclass
class ValidationReport:  # RULE-2 RULE-3
    """Aggregated output of all validation stages.

    Used by IToolValidator.rate_confidence() to compute the
    final synthesis confidence score.
    """
    ast_valid: bool = False
    no_os_imports: bool = False
    capability_match_score: float = 0.0
    security_findings: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    ast_hash: str = ""
    overall_risk_score: float = 0.0

    @property
    def allowed(self) -> bool:
        """Registration guard: all checks MUST pass (RULE 3)."""
        return (
            self.ast_valid
            and self.no_os_imports
            and self.capability_match_score >= 0.8
            and self.confidence_score >= 0.7
        )


@dataclass
class SandboxContext:  # LAW-10 RULE-2 RULE-4
    """Sandbox execution context for Phase 4 isolation.

    Defines what the sandboxed tool is allowed to do.
    """
    sandbox_id: str = ""
    allowed_capabilities: List[str] = field(default_factory=list)
    resource_limits: Dict[str, float] = field(default_factory=lambda: {
        "max_cpu_sec": 10.0,
        "max_memory_mb": 128.0,
        "max_fds": 32,
    })
    io_policy: Dict[str, Any] = field(default_factory=lambda: {
        "allowed_read_paths": [],
        "blocked_imports": ["os", "subprocess", "shutil", "signal",
                            "ctypes", "fcntl", "pty", "resource",
                            "syslog", "posix", "grp", "pwd", "spwd",
                            "socket", "urllib", "requests", "http"],
        "blocked_builtins": ["eval", "exec", "compile", "__import__"],
    })
    timeout_sec: float = 30.0
    network_mode: NetworkMode = NetworkMode.BLOCKED


@dataclass
class RegistrationPayload:  # LAW-2 LAW-14
    """Data envelope for tool registration in ToolRegistry.

    Includes compliance_proof to demonstrate all safety guards passed.
    rollback_token enables clean rollback if post-registration issues arise.
    """
    tool_id: str = ""
    signature: Dict[str, Any] = field(default_factory=dict)
    generated_code: str = ""
    ast_hash: str = ""
    capability_set: List[str] = field(default_factory=list)
    estimated_risk_score: float = 0.0
    sandbox_results: Dict[str, Any] = field(default_factory=dict)
    synthesis_trace_id: str = ""
    compliance_proof: Dict[str, Any] = field(default_factory=dict)
    rollback_token: str = ""


@dataclass
class SecurityFinding:  # RULE-2
    """A single security finding from AST / static analysis."""
    severity: ValidationSeverity = ValidationSeverity.LOW
    category: str = ""
    line: int = 0
    rule: str = ""
    detail: str = ""


@dataclass
class SynthesisReport:  # LAW-8 LAW-12
    """Report payload for EventBus publication.

    Populated by IToolSynthesizer.publish_synthesis_report().
    """
    synthesis_trace_id: str = ""
    tool_id: str = ""
    status: str = ""
    ast_hash: str = ""
    capability_set: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    registration_status: RegistrationStatus = RegistrationStatus.PENDING
    findings: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class DeterministicSynthesisGuardResult:  # RULE-1
    """Result of the Deterministic Synthesis Guard check.

    Ensures same intent + context + capability_set produces same code.
    """
    cache_hit: bool = False
    cached_code: str = ""
    cached_ast_hash: str = ""
    computed_hash: str = ""
    drift_detected: bool = False
