"""Security Interfaces — Capability Guard & IO Policy Engine Protocols.

Defines the interface contracts for capability validation and IO policy enforcement.

Ref: Phase E.1.1 — Capability Security Model & IO Policy Engine
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Protocol

if TYPE_CHECKING:
    from core.models.security import Capability, CapabilityManifest


class ICapabilityGuard(Protocol):
    """Protocol for capability-based access guard."""

    def check(
        self, tool_id: str, requested_capabilities: List[Capability]
    ) -> bool: ...

    def register_manifest(
        self, tool_id: str, manifest: CapabilityManifest
    ) -> None: ...


class IIOPolicyEngine(Protocol):
    """Protocol for IO policy enforcement engine."""

    def check_file_access(
        self, tool_id: str, path: str, mode: str
    ) -> bool: ...

    def check_network_access(
        self, tool_id: str, url: str
    ) -> bool: ...
