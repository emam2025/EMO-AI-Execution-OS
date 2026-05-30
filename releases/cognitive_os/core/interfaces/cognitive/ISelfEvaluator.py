"""
Self Evaluation Protocol — ISelfEvaluator (Interface Only).

Defines the contract for validating plan integrity and assessing risk
before plans are sent for execution. Prevents planning hallucinations.

LAW-6: every public method requires tenant_id.
LAW-11: every result is scoped by tenant_id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ValidationResult(Protocol):
    """Read-only view of a plan validation result."""

    plan_id: str
    tenant_id: str
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    validator_signature: str


@runtime_checkable
class RiskScore(Protocol):
    """Read-only view of a risk assessment."""

    assessment_id: str
    tenant_id: str
    plan_id: str
    risk_factors: List[Dict[str, Any]]
    overall_score: float
    mitigation_plan: Dict[str, Any]


class ISelfEvaluator(ABC):
    """Contract for validating plans and assessing execution risk.

    No mutation of any runtime state. Deterministic evaluation only.
    """

    @abstractmethod
    def validate_plan_integrity(
        self,
        plan: Dict[str, Any],
        tenant_id: str,
    ) -> ValidationResult:
        """Validate a plan's structural integrity and completeness.

        Args:
            plan:       The dag_blueprint or plan dict.
            tenant_id:  LAW-6 mandatory tenant scope.

        Returns:
            ValidationResult with errors/warnings and signature.
        """
        ...

    @abstractmethod
    def assess_risk(
        self,
        plan: Dict[str, Any],
        tenant_id: str,
    ) -> RiskScore:
        """Assess execution risk of a plan.

        Evaluates dependency risk, resource contention, and
        historical failure patterns. Returns a RiskScore with
        mitigation suggestions.

        Args:
            plan:       The dag_blueprint or plan dict.
            tenant_id:  LAW-6 mandatory tenant scope.

        Returns:
            RiskScore with factors, overall score, mitigation.
        """
        ...

    @abstractmethod
    def list_evaluations(
        self,
        tenant_id: str,
        plan_id: str = "",
        limit: int = 20,
    ) -> List[str]:
        """Return evaluation/assessment IDs scoped by tenant.
        LAW-11 enforced.
        """
        ...
