"""
Cognitive OS Data Models — StrategicGoal, PlanHypothesis, ReflectionEntry, RiskAssessment.

All models enforce:
- LAW-6: tenant_id mandatory on every root model.
- LAW-11: every query must scope by tenant_id.
- status mandatory for goals, risk_score mandatory for assessments.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class GoalStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        return self.value


class ReflectionSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __str__(self) -> str:
        return self.value


@dataclass
class StrategicGoal:
    """High-level goal entity for cognitive planning."""

    goal_id: str
    tenant_id: str
    project_id: str
    description: str
    priority: int = 0
    status: GoalStatus = GoalStatus.DRAFT
    parent_goal_id: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.goal_id:
            raise ValueError("goal_id is required")


@dataclass
class PlanHypothesis:
    """Concrete planning hypothesis with DAG blueprint."""

    hypothesis_id: str
    tenant_id: str
    goal_id: str
    dag_blueprint: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    validator_signature: str = ""
    project_id: str = ""
    created_at: float = field(default_factory=time.time)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.hypothesis_id:
            raise ValueError("hypothesis_id is required")
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError("confidence_score must be in [0.0, 1.0]")


@dataclass
class ReflectionEntry:
    """Record of a reflection analysis on a failure or outcome."""

    reflection_id: str
    tenant_id: str
    source_trace_id: str
    source_skill_id: str = ""
    analysis: Dict[str, Any] = field(default_factory=dict)
    strategy_update: Dict[str, Any] = field(default_factory=dict)
    severity: ReflectionSeverity = ReflectionSeverity.MEDIUM
    timestamp: float = field(default_factory=time.time)
    project_id: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.reflection_id:
            raise ValueError("reflection_id is required")


@dataclass
class RiskAssessment:
    """Risk score and mitigation plan for a plan hypothesis."""

    assessment_id: str
    tenant_id: str
    plan_id: str
    risk_factors: List[Dict[str, Any]] = field(default_factory=list)
    mitigation_plan: Dict[str, Any] = field(default_factory=dict)
    overall_score: float = 0.0
    project_id: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.assessment_id:
            raise ValueError("assessment_id is required")
        if not (0.0 <= self.overall_score <= 1.0):
            raise ValueError("overall_score must be in [0.0, 1.0]")
