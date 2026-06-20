"""Safety Gate Protocol.

Defines the interface for safety limit evaluation.

Ref: P8.1 — Safety Limits & Policy Gate
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Protocol

if TYPE_CHECKING:
    from core.models.safety import SafetyDecision, SafetyLimits


class ISafetyGate(Protocol):
    """Protocol for safety limit evaluation gate."""

    def evaluate(
        self, context: Dict[str, Any], limits: SafetyLimits
    ) -> SafetyDecision: ...
