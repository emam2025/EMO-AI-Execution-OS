"""Trust Domain Models — Trust-Aware Scheduling.

Pure data structures using stdlib only. Zero internal imports.
Frozen dataclasses for trust policies and worker classification.

Ref: Phase E.4 — Trust-Aware Scheduling
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkerTrustLevel(Enum):
    """Trust level for workers."""

    TRUSTED = "trusted"       # Fully trusted, can execute critical tasks
    VERIFIED = "verified"     # Verified identity, limited critical access
    UNVERIFIED = "unverified"  # Unknown identity, restricted to safe tasks


@dataclass(frozen=True)
class TrustPolicy:
    """Policy defining which trust levels can execute which task types."""

    task_type: str
    min_trust_level: WorkerTrustLevel
    requires_approval: bool = False
