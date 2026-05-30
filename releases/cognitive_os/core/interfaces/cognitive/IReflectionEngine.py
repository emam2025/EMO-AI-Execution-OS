"""
Reflection Engine Protocol — IReflectionEngine (Interface Only).

Defines the contract for analysing failures from R2 traces and R3 skills,
and generating corrective strategy updates. No execution, no scheduling.

LAW-6: every public method requires tenant_id.
LAW-11: every result is scoped by tenant_id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ReflectionEntry(Protocol):
    """Read-only view of a reflection analysis."""

    reflection_id: str
    tenant_id: str
    source_trace_id: str
    source_skill_id: str
    analysis: Dict[str, Any]
    strategy_update: Dict[str, Any]
    severity: str
    timestamp: float


class IReflectionEngine(ABC):
    """Contract for analysing failures and generating corrections.

    No mutation of R2/R3 memory or any runtime state.
    """

    @abstractmethod
    def analyze_failure(
        self,
        trace_id: str,
        outcome: Dict[str, Any],
        tenant_id: str,
    ) -> ReflectionEntry:
        """Analyse a failed trace or skill execution.

        Args:
            trace_id:   Source trace or skill identifier.
            outcome:    Outcome data including errors and metrics.
            tenant_id:  LAW-6 mandatory tenant scope.

        Returns:
            ReflectionEntry with analysis and severity.
        """
        ...

    @abstractmethod
    def generate_correction(
        self,
        reflection: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Generate a corrective strategy update from a reflection.

        Args:
            reflection: ReflectionEntry data dict.
            tenant_id:  LAW-6 mandatory tenant scope.

        Returns:
            StrategyUpdate dict with corrective actions.
        """
        ...

    @abstractmethod
    def list_reflections(
        self,
        tenant_id: str,
        source_skill_id: str = "",
        limit: int = 20,
    ) -> List[str]:
        """Return reflection_ids scoped by tenant_id.
        LAW-11 enforced.
        """
        ...
