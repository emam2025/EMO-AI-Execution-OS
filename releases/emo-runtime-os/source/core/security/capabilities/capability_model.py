"""Phase 4.2.1 — CapabilityModel: execution permission descriptor.

Every tool / execution has explicit capabilities. No capability
means no execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustLevel(str, Enum):
    """Trust level for workers and nodes (E4)."""
    UNVERIFIED = "unverified"
    REMOTE = "remote"
    TRUSTED = "trusted"


class AccessMode(str, Enum):
    """Filesystem access mode."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    FULL = "full"


class Scope(str, Enum):
    """Permission scope for a tool."""
    NONE = "none"
    READ = "read"
    EXECUTE = "execute"
    ADMIN = "admin"


@dataclass
class Capability:
    """Explicit permission set for an execution unit.

    Rules:
      - network=False → all network access blocked.
      - filesystem=NONE → no filesystem access.
      - subprocess=False → cannot spawn subprocesses.
      - max_cpu=0 → unlimited CPU.
      - max_memory=0 → unlimited memory.
    """

    network: bool = False
    """Allow network access (outbound requests)."""

    filesystem: AccessMode = AccessMode.NONE
    """Filesystem access level."""

    subprocess: bool = False
    """Allow spawning subprocesses."""

    max_cpu: float = 0.0
    """Max CPU time in seconds (0 = unlimited)."""

    max_memory: int = 0
    """Max memory in bytes (0 = unlimited)."""

    allowed_domains: list[str] = field(default_factory=list)
    """Domain whitelist when network=True."""

    allowed_paths: list[str] = field(default_factory=list)
    """Path whitelist when filesystem != NONE."""

    scopes: list[Scope] = field(default_factory=lambda: [Scope.EXECUTE])
    """Permission scopes this capability grants."""

    description: str = ""
    """Human-readable description of this capability set."""

    @classmethod
    def null(cls) -> Capability:
        """Capability with zero permissions — safe default."""
        return cls(scopes=[Scope.NONE])

    @classmethod
    def full(cls) -> Capability:
        """Capability with all permissions — for trusted internal tools."""
        return cls(
            network=True,
            filesystem=AccessMode.FULL,
            subprocess=True,
            max_cpu=60.0,
            max_memory=1024 * 1024 * 1024,
            scopes=[Scope.ADMIN],
            description="Full trust — all permissions granted",
        )

    @classmethod
    def restricted(cls) -> Capability:
        """Capability with minimal permissions — for untrusted external tools."""
        return cls(
            network=False,
            filesystem=AccessMode.NONE,
            subprocess=False,
            max_cpu=5.0,
            max_memory=128 * 1024 * 1024,
            scopes=[Scope.READ],
            description="Restricted — no network, no filesystem, 128MB / 5s CPU",
        )

    def has_scope(self, scope: Scope) -> bool:
        """Check if this capability includes the given scope."""
        return scope in self.scopes or Scope.ADMIN in self.scopes
