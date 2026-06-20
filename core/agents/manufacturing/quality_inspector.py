"""QualityInspectorAgent — Quality Inspection & Compliance.

Performs quality checks, quarantines defective items, enforces ISO 9001.

Ref: RC17.1.2 — Manufacturing Agents
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.models.agent import (
    AgentAudit,
    AgentCost,
    AgentIdentity,
    AgentMemory,
    AgentPermissions,
    AgentRisk,
    AgentSkills,
)
from core.models.manufacturing import QualityCheck, QualityResult

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate


class QualityInspectorAgent:
    """Quality inspector — performs checks, quarantines, enforces standards.

    Requires approval for quarantine and quarantine_release actions.
    """

    REQUIRED_APPROVAL_ACTIONS = {"quarantine_batch", "release_quarantine"}

    def __init__(
        self,
        identity: AgentIdentity,
        approval_gate: Optional[IAgentApprovalGate] = None,
    ) -> None:
        self._identity = identity
        self._approval_gate = approval_gate
        self._memory = AgentMemory()
        self._skills = AgentSkills(
            registered_tools=["quality_inspector", "defect_detector"]
        )
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_quality_checks",
                "perform_quality_check",
                "quarantine_batch",
                "release_quarantine",
                "update_quality_standard",
            ],
            requires_approval_for=["quarantine_batch", "release_quarantine"],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"
        self._quality_checks: Dict[str, QualityCheck] = {}

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    @property
    def skills(self) -> AgentSkills:
        return self._skills

    @property
    def permissions(self) -> AgentPermissions:
        return self._permissions

    @property
    def risk(self) -> AgentRisk:
        return self._risk

    @property
    def cost(self) -> AgentCost:
        return self._cost

    @property
    def audit(self) -> AgentAudit:
        return self._audit

    def activate(self) -> None:
        self._status = "active"
        self._audit.record_action(
            action="agent.activate",
            context={"agent_id": self._identity.id},
            result={"status": "active"},
        )

    def suspend(self, reason: str) -> None:
        self._status = "suspended"
        self._audit.record_action(
            action="agent.suspend",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "suspended"},
        )

    def terminate(self, reason: str) -> None:
        self._status = "terminated"
        self._audit.record_action(
            action="agent.terminate",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "terminated"},
        )

    def execute(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        ctx = context or {}
        requires_approval = task in self.REQUIRED_APPROVAL_ACTIONS

        if requires_approval and self._approval_gate is not None:
            decision = self._approval_gate.check_autonomy(
                agent_id=self._identity.id,
                action=task,
                autonomy_level="L2",
                context=ctx,
            )
            if not decision.get("allowed", False):
                self._audit.record_action(
                    action=f"agent.{task}.denied",
                    context={"agent_id": self._identity.id, "task": task},
                    result=decision,
                )
                return {"status": "denied", "reason": decision.get("reason", "")}

        self._audit.record_action(
            action=f"agent.{task}.executed",
            context={"agent_id": self._identity.id, "task": task},
            result={"status": "completed"},
        )
        return {"status": "completed", "task": task}

    def can_perform(self, action: str, context: Dict[str, Any]) -> Dict[str, Any]:
        allowed = self._permissions.can_perform(action)
        req_approval = self._permissions.requires_approval(action)
        return {
            "allowed": allowed,
            "requires_approval": req_approval,
            "reason": "Action permitted" if allowed else "Action denied",
            "policy_id": None,
        }

    def record_quality_check(self, check: QualityCheck) -> None:
        self._quality_checks[check.id] = check
        self._audit.record_action(
            action="quality_check.recorded",
            context={"check_id": check.id, "result": check.result.value},
            result={"status": "recorded"},
        )

    def get_failed_checks(self) -> List[QualityCheck]:
        return [
            c for c in self._quality_checks.values()
            if c.result == QualityResult.FAIL
        ]

    def quarantine_batch(self, check_id: str) -> Dict[str, Any]:
        check = self._quality_checks.get(check_id)
        if check is None:
            return {"status": "error", "reason": "check_not_found"}
        return self.execute("quarantine_batch", {"check_id": check_id})
