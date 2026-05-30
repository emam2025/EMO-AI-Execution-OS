"""Phase 4.1.2 — SandboxContext: execution environment descriptor.

Defines the resource constraints and isolation mode for a
sandboxed execution unit.
"""

from __future__ import annotations

import os as _os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FilesystemMode(str, Enum):
    """Filesystem access level for the sandbox."""
    READ_ONLY = "read_only"
    WRITE_TEMP = "write_temp"
    FULL = "full"
    NONE = "none"


class NetworkMode(str, Enum):
    """Network access level for the sandbox."""
    BLOCKED = "blocked"
    ALLOW_LIST = "allow_list"
    FULL = "full"


@dataclass
class SandboxContext:
    """Describes the constraints and isolation parameters for an execution.

    Default: minimal privileges (no network, no filesystem, 1s timeout).
    """

    cpu_limit: float = 1.0
    """Max CPU time in seconds (0 = unlimited)."""

    memory_limit: int = 256 * 1024 * 1024
    """Max memory in bytes (0 = unlimited). Default 256 MB."""

    timeout: float = 30.0
    """Max wall-clock time in seconds."""

    filesystem_mode: FilesystemMode = FilesystemMode.NONE
    """Filesystem access level."""

    network_mode: NetworkMode = NetworkMode.BLOCKED
    """Network access level."""

    allowed_paths: list[str] = field(default_factory=list)
    """Whitelist of filesystem paths accessible to the sandbox."""

    allowed_domains: list[str] = field(default_factory=list)
    """Whitelist of network domains accessible to the sandbox."""

    working_dir: Optional[str] = None
    """Working directory for the sandbox process."""

    environment: dict[str, str] = field(default_factory=dict)
    """Environment variables injected into the sandbox."""

    sandbox_id: str = ""
    """Optional identifier for the sandbox instance."""

    def is_network_allowed(self, domain: str) -> bool:
        """Check if a specific domain is allowed."""
        if self.network_mode == NetworkMode.FULL:
            return True
        if self.network_mode == NetworkMode.BLOCKED:
            return False
        return any(domain == d or domain.endswith(f".{d}") for d in self.allowed_domains)

    def is_path_allowed(self, path: str, write: bool = False) -> bool:
        """Check if a filesystem path is allowed."""
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
