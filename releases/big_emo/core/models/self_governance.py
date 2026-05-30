"""
Big EMO — Self-Governance Data Models.

SelfBuildProposal, AnomalyReport, RecoveryAction, SwarmAllocation.

All models enforce:
- LAW-6: tenant_id mandatory on every root model.
- tenant_id and severity mandatory for scoped queries.
- status and risk_score enforcement for SelfBuildProposal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ProposalStatus(str, Enum):
    DRAFT = "draft"
    SANDBOX_VALIDATED = "sandbox_validated"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYED = "deployed"

    def __str__(self) -> str:
        return self.value


class AnomalySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __str__(self) -> str:
        return self.value


class SwarmCoordinationState(str, Enum):
    INITIALIZING = "initializing"
    NEGOTIATING = "negotiating"
    CONSENSUS_REACHED = "consensus_reached"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value


@dataclass
class SelfBuildProposal:
    proposal_id: str
    tenant_id: str
    intent: str
    tool_draft: Dict[str, Any] = field(default_factory=dict)
    risk_score: float = 0.0
    status: ProposalStatus = ProposalStatus.DRAFT
    project_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.proposal_id:
            raise ValueError("proposal_id is required")
        if not (0.0 <= self.risk_score <= 1.0):
            raise ValueError("risk_score must be in [0.0, 1.0]")


@dataclass
class AnomalyReport:
    report_id: str
    tenant_id: str
    source_service: str
    anomaly_type: str = ""
    severity: AnomalySeverity = AnomalySeverity.MEDIUM
    mitigation: str = ""
    project_id: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.report_id:
            raise ValueError("report_id is required")
        if not self.source_service:
            raise ValueError("source_service is required")


@dataclass
class RecoveryAction:
    action_id: str
    tenant_id: str
    target_service: str
    correction_steps: List[str] = field(default_factory=list)
    validator_signature: str = ""
    project_id: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.action_id:
            raise ValueError("action_id is required")
        if not self.target_service:
            raise ValueError("target_service is required")
        if not self.validator_signature:
            raise ValueError("validator_signature is required (LAW-22)")


@dataclass
class SwarmAllocation:
    allocation_id: str
    tenant_id: str
    task_id: str
    agent_assignments: List[Dict[str, Any]] = field(default_factory=list)
    coordination_state: SwarmCoordinationState = SwarmCoordinationState.INITIALIZING
    project_id: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.allocation_id:
            raise ValueError("allocation_id is required")
        if not self.task_id:
            raise ValueError("task_id is required")
