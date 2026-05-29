"""CriticAgent — concrete implementation of ICriticAgent.

LAW 9: Critic evaluates constraints passed as data — no governance invocation.
RULE 3: Must NEVER accept cross-tenant plan without scope_verified.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional


class CriticAgent:  # LAW-9 RULE-3
    """Evaluates plan proposals against constraints and safety.

    Per-instance state. No global caches.
    """

    def __init__(self) -> None:
        self._reviews: Dict[str, Dict[str, Any]] = {}

    async def evaluate_plan(
        self,
        proposal: Dict[str, Any],
        constraints: Dict[str, Any],
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not tenant_id:
            return {"status": "error", "message": "tenant_id required"}

        violations: List[Dict[str, Any]] = []
        fixes: List[str] = []

        # Scope check: cross-tenant context requires scope_verified
        proposal_tenant = proposal.get("tenant_id", "")
        if proposal_tenant and proposal_tenant != tenant_id:
            violations.append({
                "rule_ref": "G-P2",
                "severity": "error",
                "description": f"Cross-tenant proposal: expected {tenant_id}, got {proposal_tenant}",
            })
            fixes.append("Set scope_verified=True or ensure tenant_id match")

        # Budget constraint
        budget_limit = constraints.get("max_cost_units", None)
        if budget_limit is not None:
            est = float(proposal.get("estimated_cost", "0"))
            if est > float(budget_limit):
                violations.append({
                    "rule_ref": "budget",
                    "severity": "warning",
                    "description": f"Estimated cost {est} exceeds budget {budget_limit}",
                })
                fixes.append("Reduce DAG node count or simplify tools")

        # Node count sanity
        nodes = proposal.get("dag_nodes", [])
        if len(nodes) > 100:
            violations.append({
                "rule_ref": "complexity",
                "severity": "warning",
                "description": f"Excessive node count: {len(nodes)}",
            })
            fixes.append("Split into sub-plans or prune unused nodes")

        # Intent match
        intent = proposal.get("intent", "")
        if not intent or len(intent.strip()) < 2:
            violations.append({
                "rule_ref": "intent",
                "severity": "error",
                "description": "Intent too short or empty",
            })
            fixes.append("Provide a descriptive intent string")

        is_valid = len([v for v in violations if v["severity"] == "error"]) == 0
        risk = "critical" if any(v["severity"] == "error" for v in violations) else \
               "high" if any(v["severity"] == "warning" for v in violations) else "low"

        report = {
            "proposal_id": proposal.get("proposal_id", ""),
            "is_valid": is_valid,
            "violations": violations,
            "suggested_fixes": fixes,
            "risk_level": risk,
            "trace_id": cognitive_trace_id,
            "cognitive_trace_id": cognitive_trace_id,
            "tenant_id": tenant_id,
        }
        self._reviews[proposal.get("proposal_id", "")] = report
        return report

    async def reject_with_reason(
        self,
        proposal: Dict[str, Any],
        violation: str,
        tenant_id: str,
        scope_verified: bool = False,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not tenant_id:
            return {"status": "error", "message": "tenant_id required"}
        # STOP-CONDITION: RULE 3 — must refuse if cross-tenant without scope_verified
        proposal_tenant = proposal.get("tenant_id", "")
        if proposal_tenant and proposal_tenant != tenant_id and not scope_verified:
            return {
                "status": "blocked",
                "message": "RULE 3: Cannot reject cross-tenant plan without scope_verified=True",
                "cognitive_trace_id": cognitive_trace_id,
            }

        return {
            "status": "rejected",
            "proposal_id": proposal.get("proposal_id", ""),
            "reason": violation,
            "violation_code": "critic_rejection",
            "is_blocking": True,
            "scope_verified": scope_verified,
            "cognitive_trace_id": cognitive_trace_id,
            "tenant_id": tenant_id,
        }
