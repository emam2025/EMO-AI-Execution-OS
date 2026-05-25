"""Phase G4 — Tool Synthesis Agent: Runtime Models.  # LAW-11 LAW-12 LAW-14

Shared types used by all G4 components: ToolSynthesizer, ToolValidator,
ToolSandboxer, ToolRegistryManager, and SynthesisStateMachine.

Mirrors artifacts/design/g4/models/02_synthesis_and_tool_models.py
for runtime importability.

Ref: Canon LAW 11 (No Global State), LAW 12 (Traceability)
Ref: Canon LAW 14 (Resource Governance), RULE 1-4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SynthesisSignal(str, Enum):  # LAW-8
    APPROVE = "approve"
    REJECT_CODE = "reject_code"
    REJECT_SECURITY = "reject_security"
    REQUIRE_REVISION = "require_revision"
    ESCALATE = "escalate"


class SynthesisState(str, Enum):  # LAW-14
    INTENT_RECEIVED = "intent_received"
    CODE_GENERATION = "code_generation"
    AST_VALIDATION = "ast_validation"
    SECURITY_SCAN = "security_scan"
    SANDBOX_DRY_RUN = "sandbox_dry_run"
    REGISTER = "register"
    REJECT = "reject"
    ESCALATE = "escalate"


class ValidationSeverity(str, Enum):  # RULE-2
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NetworkMode(str, Enum):  # RULE-2 RULE-4
    BLOCKED = "blocked"
    ISOLATED = "isolated"


class RegistrationStatus(str, Enum):  # LAW-2 LAW-14
    REGISTERED = "registered"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    PENDING = "pending"


@dataclass
class SynthesizedTool:  # LAW-12 LAW-14
    tool_id: str = ""
    synthesis_trace_id: str = ""
    plan_id: str = ""
    intent_id: str = ""
    generated_code: str = ""
    ast_hash: str = ""
    capability_set: List[str] = field(default_factory=list)
    estimated_risk_score: float = 0.0
    ast_valid: bool = False
    no_os_imports: bool = False
    capability_match_score: float = 0.0
    security_findings: List[Dict[str, Any]] = field(default_factory=list)
    sandbox_test_results: Dict[str, Any] = field(default_factory=dict)
    registration_status: RegistrationStatus = RegistrationStatus.PENDING
    registration_id: str = ""
    rollback_token: str = ""
    compliance_proof: Dict[str, Any] = field(default_factory=dict)
    g1_planner_trace_id: str = ""
    g3_optimizer_trace_id: str = ""


@dataclass
class ValidationReport:  # RULE-2 RULE-3
    ast_valid: bool = False
    no_os_imports: bool = False
    capability_match_score: float = 0.0
    security_findings: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    ast_hash: str = ""
    overall_risk_score: float = 0.0

    @property
    def allowed(self) -> bool:
        return (
            self.ast_valid
            and self.no_os_imports
            and self.capability_match_score >= 0.8
            and self.confidence_score >= 0.7
        )


@dataclass
class SandboxContext:  # LAW-10 RULE-2 RULE-4
    sandbox_id: str = ""
    allowed_capabilities: List[str] = field(default_factory=list)
    resource_limits: Dict[str, float] = field(default_factory=lambda: {
        "max_cpu_sec": 10.0,
        "max_memory_mb": 128.0,
        "max_fds": 32,
    })
    io_policy: Dict[str, Any] = field(default_factory=lambda: {
        "allowed_read_paths": [],
        "blocked_imports": [
            "os", "subprocess", "shutil", "signal", "ctypes", "fcntl",
            "pty", "resource", "syslog", "posix", "grp", "pwd", "spwd",
            "socket", "urllib", "requests", "http",
        ],
        "blocked_builtins": ["eval", "exec", "compile", "__import__"],
    })
    timeout_sec: float = 30.0
    network_mode: NetworkMode = NetworkMode.BLOCKED


@dataclass
class RegistrationPayload:  # LAW-2 LAW-14
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
    severity: ValidationSeverity = ValidationSeverity.LOW
    category: str = ""
    line: int = 0
    rule: str = ""
    detail: str = ""


@dataclass
class SynthesisReport:  # LAW-8 LAW-12
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
    cache_hit: bool = False
    cached_code: str = ""
    cached_ast_hash: str = ""
    computed_hash: str = ""
    drift_detected: bool = False
