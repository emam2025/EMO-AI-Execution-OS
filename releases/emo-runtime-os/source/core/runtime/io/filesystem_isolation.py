"""Phase 4.3.3 — FilesystemIsolation: path whitelist and access control.

Controls filesystem access based on path whitelists, read/write
restrictions, and virtual filesystem mapping.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from core.runtime.io.io_policy_engine import IOViolation

logger = logging.getLogger("emo_ai.io.filesystem")


class FileAccessViolation(IOViolation):
    """Raised when a filesystem access is blocked."""

    def __init__(self, path: str, mode: str, reason: str, tool: str = ""):
        super().__init__(f"filesystem:{mode}:{path}", reason, tool)


class AccessLevel(str, Enum):
    """Filesystem access level."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    FULL = "full"


@dataclass
class FilesystemPolicy:
    """Filesystem access policy for a tool."""
    access_level: AccessLevel = AccessLevel.NONE
    allowed_paths: List[str] = field(default_factory=list)
    allowed_extensions: List[str] = field(default_factory=list)
    max_file_size: int = 0
    block_symlinks: bool = True


class FilesystemIsolation:
    """Controls filesystem access for sandboxed execution.

    Enforces:
      - Path whitelists
      - Read/write restrictions
      - File extension filters
      - Symlink blocking
    """

    def __init__(self) -> None:
        self._policies: dict = {}
        self._default_policy = FilesystemPolicy()
        self._virtual_mappings: dict = {}

    def set_policy(self, tool: str, policy: FilesystemPolicy) -> None:
        """Set the filesystem policy for a tool."""
        self._policies[tool] = policy

    def map_virtual(self, virtual_path: str, real_path: str) -> None:
        """Map a virtual path to a real path."""
        self._virtual_mappings[virtual_path] = real_path

    def resolve_path(self, path: str) -> str:
        """Resolve a potentially virtual path to a real path."""
        for vp, rp in self._virtual_mappings.items():
            if path.startswith(vp):
                return path.replace(vp, rp, 1)
        return os.path.abspath(path)

    def check_read(self, tool: str, path: str) -> str:
        """Check if a file can be read. Returns resolved path or raises."""
        policy = self._policies.get(tool, self._default_policy)
        resolved = self.resolve_path(path)

        if policy.access_level == AccessLevel.NONE:
            raise FileAccessViolation(path, "read", "Filesystem access denied", tool)

        if policy.access_level == AccessLevel.WRITE:
            raise FileAccessViolation(path, "read", "Write-only access", tool)

        self._check_path_allowed(tool, resolved, policy)
        return resolved

    def check_write(self, tool: str, path: str) -> str:
        """Check if a file can be written. Returns resolved path or raises."""
        policy = self._policies.get(tool, self._default_policy)
        resolved = self.resolve_path(path)

        if policy.access_level in (AccessLevel.NONE, AccessLevel.READ):
            raise FileAccessViolation(path, "write", "Write access denied", tool)

        self._check_path_allowed(tool, resolved, policy)
        return resolved

    def _check_path_allowed(
        self,
        tool: str,
        path: str,
        policy: FilesystemPolicy,
    ) -> None:
        if policy.allowed_paths:
            path_match = any(
                path.startswith(os.path.abspath(p))
                for p in policy.allowed_paths
            )
            if not path_match:
                raise FileAccessViolation(
                    path, "access", f"Path not in whitelist: {path}", tool,
                )

        if policy.allowed_extensions:
            ext = os.path.splitext(path)[1].lower()
            if ext and ext not in policy.allowed_extensions:
                raise FileAccessViolation(
                    path, "access",
                    f"Extension {ext} not allowed: {policy.allowed_extensions}",
                    tool,
                )

        if policy.block_symlinks and os.path.islink(path):
            raise FileAccessViolation(
                path, "access", "Symlinks are blocked", tool,
            )
