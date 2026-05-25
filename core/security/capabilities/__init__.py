"""Phase 4.2 — Capability Security Model."""

from core.security.capabilities.capability_model import (
    Capability,
    AccessMode,
    Scope,
    TrustLevel,
)
from core.security.capabilities.capability_registry import (
    CapabilityRegistry,
    DEFAULT_CAPABILITY,
)
from core.security.capabilities.capability_guard import (
    CapabilityGuard,
    CapabilityViolation,
)
from core.security.capabilities.sensitive_tools import (
    SensitiveToolRegistry,
    Sensitivity,
)

__all__ = [
    "Capability",
    "AccessMode",
    "Scope",
    "CapabilityRegistry",
    "DEFAULT_CAPABILITY",
    "CapabilityGuard",
    "CapabilityViolation",
    "SensitiveToolRegistry",
    "Sensitivity",
]
