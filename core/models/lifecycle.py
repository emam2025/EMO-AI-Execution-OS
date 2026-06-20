"""Lifecycle Domain Models.

Pure data structures using stdlib only. Zero internal imports.

Ref: P10.2 — Reliability & Graceful Lifecycle
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ComponentStatus(Enum):
    """Status of a managed component."""

    STARTING = "starting"
    READY = "ready"
    DEGRADING = "degrading"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass(frozen=True)
class HealthCheckResult:
    """Result of a health check probe."""

    component_name: str = ""
    status: ComponentStatus = ComponentStatus.READY
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
