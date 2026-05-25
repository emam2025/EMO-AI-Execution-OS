"""Phase 4.2 — Security & Capability System."""

from core.security.capabilities import (
    Capability,
    AccessMode,
    CapabilityRegistry,
    DEFAULT_CAPABILITY,
    CapabilityGuard,
    CapabilityViolation,
)

__all__ = [
    "Capability",
    "AccessMode",
    "CapabilityRegistry",
    "DEFAULT_CAPABILITY",
    "CapabilityGuard",
    "CapabilityViolation",
]
