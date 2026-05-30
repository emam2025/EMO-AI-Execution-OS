"""
Self Evaluator — ISelfEvaluator implementation.

Validates plan integrity, assesses execution risk, and enforces
planning safety bounds. No execution. No scheduling.
LAW-6 enforced on all public methods.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from releases.cognitive_os.core.interfaces.cognitive.ISelfEvaluator import ISelfEvaluator
from releases.cognitive_os.core.models.cognitive import RiskAssessment


@dataclass
class ValidationResult:
    plan_id: str = ""
    tenant_id: str = ""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validator_signature: str = ""


@dataclass
class RiskScore:
    assessment_id: str = ""
    tenant_id: str = ""
    plan_id: str = ""
    risk_factors: List[Dict[str, Any]] = field(default_factory=list)
    overall_score: float = 0.0
    mitigation_plan: Dict[str, Any] = field(default_factory=dict)


class SelfEvaluator(ISelfEvaluator):
    """Validates plan integrity and assesses risk.

    LAW-6: every public method requires tenant_id.
    Zero state mutation — all validation is deterministic.
    """

    def __init__(self) -> None:
        self._evaluations: Dict[str, RiskAssessment] = {}

    def validate_plan_integrity(
        self,
        plan: Dict[str, Any],
        tenant_id: str,
    ) -> ValidationResult:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        errors: List[str] = []
        warnings: List[str] = []
        dag = plan.get("dag", plan)
        nodes = dag.get("nodes", [])
        edges = dag.get("edges", [])
        node_ids = {n["id"] for n in nodes}
        if not nodes:
            errors.append("Plan has no nodes in DAG")
        for n in nodes:
            if not n.get("id"):
                errors.append("Node missing 'id' field")
            if not n.get("tool"):
                warnings.append(f"Node '{n.get('id', '?')}' missing 'tool'")
        for e in edges:
            missing = []
            if e.get("from") not in node_ids:
                missing.append(f"from='{e.get('from')}'")
            if e.get("to") not in node_ids:
                missing.append(f"to='{e.get('to')}'")
            if missing:
                errors.append(f"Edge references non-existent nodes: {', '.join(missing)}")
        if edges:
            from collections import Counter
            in_deg = Counter(e["to"] for e in edges)
            out_deg = Counter(e["from"] for e in edges)
            no_in = [nid for nid in node_ids if in_deg.get(nid, 0) == 0 and out_deg.get(nid, 0) > 0]
            if not no_in:
                warnings.append("No source node found; possible circular dependency")
        plan_id = plan.get("hypothesis_id", plan.get("plan_id", f"plan-{uuid.uuid4().hex[:12]}"))
        sig = hashlib.sha256(
            json.dumps({"plan_id": plan_id, "errors": errors}, sort_keys=True).encode()
        ).hexdigest()[:32]
        return ValidationResult(
            plan_id=plan_id,
            tenant_id=tenant_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            validator_signature=sig,
        )

    def assess_risk(
        self,
        plan: Dict[str, Any],
        tenant_id: str,
    ) -> RiskScore:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        dag = plan.get("dag", plan)
        nodes = dag.get("nodes", [])
        edges = dag.get("edges", [])
        risk_factors: List[Dict[str, Any]] = []
        score = 0.0
        if len(nodes) >= 5:
            risk_factors.append({
                "factor": "complexity",
                "severity": min((len(nodes) - 4) * 0.1, 0.5),
                "description": f"High node count ({len(nodes)}) increases execution risk",
            })
            score += len(nodes) * 0.05
        if len(edges) >= 8:
            risk_factors.append({
                "factor": "dependency_density",
                "severity": min(len(edges) * 0.05, 0.4),
                "description": f"High edge count ({len(edges)}) suggests tight coupling",
            })
            score += len(edges) * 0.03
        if edges:
            from collections import Counter
            in_deg = Counter(e["to"] for e in edges)
            max_fan_in = max(in_deg.values())
            if max_fan_in >= 3:
                risk_factors.append({
                    "factor": "fan_in",
                    "severity": min(max_fan_in * 0.1, 0.3),
                    "description": f"Node with fan-in {max_fan_in} creates bottleneck risk",
                })
                score += max_fan_in * 0.05
        if not risk_factors:
            risk_factors.append({
                "factor": "trivial",
                "severity": 0.05,
                "description": "Plan is trivial; low risk anticipated",
            })
            score = 0.05
        overall_score = min(round(score, 4), 0.95)
        plan_id = plan.get("hypothesis_id", plan.get("plan_id", f"plan-{uuid.uuid4().hex[:12]}"))
        assessment_id = f"ra-{uuid.uuid4().hex[:16]}"
        mitigation = {
            "suggested_actions": ["reduce_node_count", "flatten_dependencies"] if len(nodes) >= 5 else [],
            "max_accepted_score": 0.75,
            "current_score": overall_score,
        }
        risk_score = RiskScore(
            assessment_id=assessment_id,
            tenant_id=tenant_id,
            plan_id=plan_id,
            risk_factors=risk_factors,
            overall_score=overall_score,
            mitigation_plan=mitigation,
        )
        assessment = RiskAssessment(
            assessment_id=assessment_id,
            tenant_id=tenant_id,
            plan_id=plan_id,
            risk_factors=risk_factors,
            mitigation_plan=mitigation,
            overall_score=overall_score,
        )
        self._evaluations[assessment_id] = assessment
        return risk_score

    def list_evaluations(
        self,
        tenant_id: str,
        plan_id: str = "",
        limit: int = 20,
    ) -> List[str]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        results: List[str] = []
        for assess in self._evaluations.values():
            if assess.tenant_id != tenant_id:
                continue
            if plan_id and assess.plan_id != plan_id:
                continue
            results.append(assess.assessment_id)
        return results[:limit]

    def get_assessment(
        self,
        assessment_id: str,
        tenant_id: str,
    ) -> RiskAssessment:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        assess = self._evaluations.get(assessment_id)
        if not assess or assess.tenant_id != tenant_id:
            raise KeyError(f"Assessment not found: {assessment_id}")
        return assess
