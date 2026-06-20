"""Rollback Domain Models.

Pure data structures using stdlib only. Zero internal imports.

Ref: P8.3 — Rollback & Containment
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


class RollbackScope(Enum):
    """Scope of rollback action."""

    NODE = "node"
    SESSION = "session"
    AGENT = "agent"
    GLOBAL = "global"


class RollbackStatus(Enum):
    """Status of a rollback action."""

    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass(frozen=True)
class RollbackAction:
    """Record of a rollback action with audit trail."""

    action_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scope: RollbackScope = RollbackScope.NODE
    target_id: str = ""
    reason: str = ""
    status: RollbackStatus = RollbackStatus.PENDING
