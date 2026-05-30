"""
Self-Builder Engine — ISelfBuilder implementation.

Analyses intents, generates tool drafts, and validates against
sandbox guards. No execution, no scheduling.
LAW-6 enforced on all public methods.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from releases.big_emo.core.interfaces.self_governance.ISelfBuilder import ISelfBuilder
from releases.big_emo.core.models.self_governance import (
    ProposalStatus,
    SelfBuildProposal,
)


@dataclass
class ToolDraftData:
    draft_id: str = ""
    tenant_id: str = ""
    intent: str = ""
    tool_spec: Dict[str, Any] = field(default_factory=dict)
    risk_score: float = 0.0
    status: str = "draft"


@dataclass
class BuildRecord:
    record_id: str = ""
    tenant_id: str = ""
    proposal_id: str = ""
    tool_draft_id: str = ""
    validator_signature: str = ""
    status: str = ""
    timestamp: float = 0.0


class _SandboxGuard:
    """Internal sandbox validation rules."""

    FORBIDDEN_TOOLS = {"exec_shell", "run_code", "access_secret", "modify_tenant_data"}
    FORBIDDEN_PERMISSIONS = {"admin", "super_admin", "cross_tenant_read", "exec_engine_access"}
    MAX_STEPS = 10
    MAX_DEPENDENCIES = 5

    @staticmethod
    def check_permissions(spec: dict) -> List[str]:
        violations = []
        perms = spec.get("permissions", [])
        for p in perms:
            if p.lower() in _SandboxGuard.FORBIDDEN_PERMISSIONS:
                violations.append(f"forbidden permission: {p}")
        return violations

    @staticmethod
    def check_tools(spec: dict) -> List[str]:
        violations = []
        tools = spec.get("requires_tools", [])
        for t in tools:
            if t.lower() in _SandboxGuard.FORBIDDEN_TOOLS:
                violations.append(f"forbidden tool: {t}")
        return violations

    @staticmethod
    def check_dependencies(spec: dict) -> List[str]:
        violations = []
        deps = spec.get("dependencies", [])
        if len(deps) > _SandboxGuard.MAX_DEPENDENCIES:
            violations.append(f"exceeded max dependencies ({len(deps)} > {_SandboxGuard.MAX_DEPENDENCIES})")
        return violations

    @staticmethod
    def check_steps(spec: dict) -> List[str]:
        violations = []
        steps = spec.get("steps", [])
        if len(steps) > _SandboxGuard.MAX_STEPS:
            violations.append(f"exceeded max steps ({len(steps)} > {_SandboxGuard.MAX_STEPS})")
        return violations


class SelfBuilderEngine(ISelfBuilder):
    """Analyses intents and generates sandbox-validated tool drafts.

    LAW-6: every public method requires tenant_id.
    LAW-20: sandbox validation mandatory.
    """

    def __init__(self) -> None:
        self._proposals: Dict[str, SelfBuildProposal] = {}
        self._records: Dict[str, BuildRecord] = {}

    def propose_tool(
        self,
        intent: str,
        tenant_id: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> ToolDraftData:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not intent:
            raise ValueError("intent is required")
        constraints = constraints or {}
        tool_spec = self._parse_intent(intent, constraints)
        risk_score = self._compute_risk(tool_spec)
        draft_id = f"draft-{uuid.uuid4().hex[:16]}"
        tool_draft = ToolDraftData(
            draft_id=draft_id,
            tenant_id=tenant_id,
            intent=intent,
            tool_spec=tool_spec,
            risk_score=risk_score,
            status=ProposalStatus.DRAFT.value,
        )
        proposal_id = f"proposal-{uuid.uuid4().hex[:12]}"
        proposal = SelfBuildProposal(
            proposal_id=proposal_id,
            tenant_id=tenant_id,
            intent=intent,
            tool_draft=tool_spec,
            risk_score=risk_score,
            status=ProposalStatus.DRAFT,
        )
        self._proposals[proposal_id] = proposal
        return tool_draft

    def validate_sandbox(
        self,
        draft: Dict[str, Any],
        tenant_id: str,
    ) -> bool:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        spec = draft.get("tool_spec", draft)
        violations = (
            _SandboxGuard.check_permissions(spec)
            + _SandboxGuard.check_tools(spec)
            + _SandboxGuard.check_dependencies(spec)
            + _SandboxGuard.check_steps(spec)
        )
        return len(violations) == 0

    def record_build(
        self,
        proposal: Dict[str, Any],
        validator_signature: str,
        tenant_id: str,
    ) -> BuildRecord:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not validator_signature:
            raise ValueError("validator_signature is required (LAW-20)")
        record = BuildRecord(
            record_id=f"br-{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            proposal_id=proposal.get("proposal_id", proposal.get("draft_id", "")),
            tool_draft_id=proposal.get("draft_id", ""),
            validator_signature=validator_signature,
            status=ProposalStatus.APPROVED.value,
            timestamp=__import__("time").time(),
        )
        self._records[record.record_id] = record
        return record

    def get_proposal(
        self,
        proposal_id: str,
        tenant_id: str,
    ) -> SelfBuildProposal:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        prop = self._proposals.get(proposal_id)
        if not prop or prop.tenant_id != tenant_id:
            raise KeyError(f"Proposal not found: {proposal_id}")
        return prop

    def _parse_intent(self, intent: str, constraints: dict) -> Dict[str, Any]:
        import re
        tokens = re.sub(r"[,.!?;:]+", " ", intent.lower()).split()
        suggested_tools = {"analyse": "analyzer", "build": "builder", "deploy": "deployer", "monitor": "monitor"}
        selected = []
        for t in tokens:
            if t in suggested_tools and t not in selected:
                selected.append(t)
        if not selected:
            selected = ["process"]
        return {
            "intent": intent,
            "steps": [{"action": s, "tool": suggested_tools.get(s, "generic")} for s in selected],
            "requires_tools": [suggested_tools.get(s, "generic") for s in selected],
            "permissions": constraints.get("permissions", ["read"]),
            "dependencies": constraints.get("dependencies", []),
        }

    def _compute_risk(self, spec: dict) -> float:
        score = 0.1
        score += len(spec.get("steps", [])) * 0.05
        score += len(spec.get("requires_tools", [])) * 0.05
        if "write" in spec.get("permissions", []):
            score += 0.1
        if len(spec.get("dependencies", [])) > 2:
            score += 0.1
        return min(round(score, 4), 0.95)
