"""Safety Domain Models.

Pure data structures using stdlib only. Zero internal imports.

Ref: P8.1 — Safety Limits & Policy Gate
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SafetyLimitType(Enum):
    """Types of safety limits that can be enforced."""

    TOKEN_LIMIT = "token_limit"
    COST_LIMIT = "cost_limit"
    RUNTIME_LIMIT = "runtime_limit"
    POLICY_VIOLATION = "policy_violation"


@dataclass(frozen=True)
class SafetyLimits:
    """Configurable safety thresholds for execution."""

    max_tokens: int = 100_000
    max_cost_usd: float = 10.0
    max_runtime_seconds: float = 3600.0


@dataclass(frozen=True)
class SafetyDecision:
    """Result of a safety gate evaluation."""

    allowed: bool
    reason: str
    violation_type: Optional[SafetyLimitType] = None
