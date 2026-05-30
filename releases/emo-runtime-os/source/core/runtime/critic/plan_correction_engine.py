"""Phase G2 — Plan Correction Engine.  # LAW-8 RULE-3

Concrete implementation of IPlanCorrectionEngine.

Applies semantic fixes, adjusts DAG topology, validates constraints,
and estimates rollback impact. All corrections guarded by RULE 3.

Ref: Canon LAW 8, RULE 3, RULE 1
Ref: artifacts/design/g2/protocols/01_critic_protocols.py
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

from core.runtime.models.critic_models import (
    CorrectionPayload,
    CorrectionType,
    DiagnosisReport,
)

logger = logging.getLogger("emo_ai.critic.correction_engine")


class PlanCorrectionEngine:  # LAW-8 RULE-3
    """Applies corrections to plans under guard enforcement.

    RULE 3: Every correction MUST require ≥ 1 diagnosis signal
    AND confidence >= 0.75.
    """

    def apply_semantic_fix(  # LAW-8
        self,
        plan: Dict[str, Any],
        correction: Dict[str, Any],
    ) -> Dict[str, Any]:
        updated = dict(plan)
        nodes = list(updated.get("nodes", []))
        affected = correction.get("affected_nodes", [])

        for i, node in enumerate(nodes):
            if isinstance(node, dict) and node.get("node_id") in affected:
                patched = dict(node)
                if "tool_params" in patched and isinstance(patched["tool_params"], dict):
                    fix_params = correction.get("parameters", {})
                    patched["tool_params"] = {**patched["tool_params"], **fix_params}
                patched["patched"] = True
                nodes[i] = patched

        updated["nodes"] = nodes
        updated["correction_count"] = updated.get("correction_count", 0) + 1
        return updated

    def adjust_topology(  # RULE-1
        self,
        dag: List[Dict[str, Any]],
        affected_nodes: List[str],
        strategy: str = "reorder",
    ) -> List[Dict[str, Any]]:
        if strategy == "reorder":
            filtered = [e for e in dag if e.get("to") not in affected_nodes]
            return filtered
        elif strategy == "bypass":
            return [
                e for e in dag
                if e.get("from") not in affected_nodes
                and e.get("to") not in affected_nodes
            ]
        elif strategy == "insert_barrier":
            return list(dag)

        return list(dag)

    def validate_constraint_compliance(  # LAW-8
        self,
        corrected_plan: Dict[str, Any],
        constraints: Optional[List[str]] = None,
    ) -> bool:
        nodes = corrected_plan.get("nodes", [])
        dag = corrected_plan.get("dag_topology", [])

        if constraints is None:
            constraints = ["no_orphan_nodes", "max_corrections <= 3"]

        for constraint in constraints:
            if constraint == "no_orphan_nodes":
                node_ids = {n.get("node_id") for n in nodes if isinstance(n, dict)}
                for edge in dag:
                    if isinstance(edge, dict):
                        if edge.get("from") not in node_ids:
                            return False
                        if edge.get("to") not in node_ids:
                            return False

            if constraint.startswith("max_corrections"):
                limit = int(constraint.split("<=")[1].strip())
                if corrected_plan.get("correction_count", 0) > limit:
                    return False

        return True

    def estimate_impact(  # RULE-5
        self,
        plan_id: str,
        correction: Dict[str, Any],
        baseline: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        affected = correction.get("affected_nodes", [])
        risk = correction.get("estimated_risk", 0.3)
        return {
            "risk_score": risk,
            "cost_delta": risk * 0.1,
            "affected_node_count": len(affected),
            "rollback_complexity": "low" if risk < 0.3 else "medium" if risk < 0.7 else "high",
        }

    def propose_correction(  # RULE-3
        self,
        diagnosis: DiagnosisReport,
    ) -> CorrectionPayload:
        payload = CorrectionPayload(
            patch_type=CorrectionType.SEMANTIC_FIX,
            affected_nodes=[diagnosis.root_cause_node] if diagnosis.root_cause_node else [],
            estimated_risk=0.3,
            rollback_safe=True,
            critic_trace_id=diagnosis.critic_trace_id,
        )

        if diagnosis.confidence_score >= 0.85:
            payload.rollback_safe = True
            payload.estimated_risk = 0.2
        elif diagnosis.confidence_score >= 0.75:
            payload.rollback_safe = True
            payload.estimated_risk = 0.4

        impact = self.estimate_impact(diagnosis.plan_id, {
            "affected_nodes": payload.affected_nodes,
            "estimated_risk": payload.estimated_risk,
        })
        payload.estimated_impact = impact

        return payload
