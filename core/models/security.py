"""Security Domain Models — Capability Security & IO Policy.

Pure data structures using stdlib only. Zero internal imports.
Frozen dataclasses for capability manifests and security violations.

Ref: Phase E.1.1 — Capability Security Model & IO Policy Engine
Ref: Phase E.2 — Advanced Capability Security (Dynamic Sensitive Tool Classification)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class Capability(Enum):
    """Tool execution capabilities — explicit permission set."""

    NETWORK_OUTBOUND = "network_outbound"
    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"
    SUBPROCESS = "subprocess"
    EXECUTE_SENSITIVE = "execute_sensitive"


class ToolSensitivityLevel(Enum):
    """Sensitivity classification for registered tools.

    LOW: Read-only tools, no side effects (e.g., metric_reader).
    MEDIUM: Tools with limited side effects (e.g., data_transformer).
    HIGH: Tools with significant side effects (e.g., config_updater).
    CRITICAL: Tools with irreversible or safety-critical side effects
              (e.g., line_shutdown, emergency_stop).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ViolationAction(Enum):
    """Action taken when a security violation is detected."""

    BLOCKED = "blocked"
    AUDITED = "audited"


@dataclass(frozen=True)
class CapabilityManifest:
    """Capability manifest for a registered tool.

    Defines the exact capabilities a tool is allowed to use,
    along with resource limits and sensitivity classification.
    """

    tool_id: str = ""
    allowed_capabilities: tuple = ()
    max_cpu_seconds: float = 0.0
    max_memory_mb: int = 0
    sensitivity_level: ToolSensitivityLevel = ToolSensitivityLevel.LOW


@dataclass(frozen=True)
class SecurityViolation:
    """Record of a security violation detected by guard or policy engine."""

    violation_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tool_id: str = ""
    requested_capability: str = ""
    reason: str = ""
    action_taken: ViolationAction = ViolationAction.BLOCKED
    sensitivity_level: ToolSensitivityLevel = ToolSensitivityLevel.LOW
