"""Guardrails Engine Protocol.

Defines the interface for behavioral and performance monitoring.

Ref: P8.2 — Guardrails Engine
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

if TYPE_CHECKING:
    from core.models.guardrails import GuardrailAlert


class IGuardrailsEngine(Protocol):
    """Protocol for guardrails monitoring engine."""

    def evaluate_behavior(
        self, agent_id: str, recent_actions: List[Dict[str, Any]]
    ) -> Optional[GuardrailAlert]: ...

    def evaluate_performance(
        self, agent_id: str, metrics: Dict[str, float]
    ) -> Optional[GuardrailAlert]: ...

    def record_baseline(self, agent_id: str, baseline_metrics: Dict[str, float]) -> None: ...
