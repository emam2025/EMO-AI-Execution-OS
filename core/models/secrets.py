"""Secrets Domain Models — Ephemeral Secret Injection.

Pure data structures using stdlib only. Zero internal imports.
Frozen dataclasses for secret references and access control.

Ref: Phase E.3 — Secrets Runtime (Ephemeral Secret Injection)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SecretScope(Enum):
    """Scope of secret access."""

    TOOL = "tool"       # Secret available only during tool execution
    SESSION = "session"  # Secret available for entire session
    GLOBAL = "global"    # Secret available system-wide (discouraged)


@dataclass(frozen=True)
class SecretRef:
    """Reference to a secret (not the secret itself).

    Defines access scope, expiration, and allowed tools.
    The actual secret value is never exposed in this structure.
    """

    secret_id: str
    scope: SecretScope = SecretScope.TOOL
    expiration_seconds: float = 3600.0
    allowed_tools: tuple = ()
