"""
Strategic Planner — IStrategicPlanner implementation.

Decomposes high-level goals into DAG execution plans with feasibility
evaluation. No scheduling, no execution. LAW-6 enforced on all public
methods.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional

from releases.cognitive_os.core.interfaces.cognitive.IStrategicPlanner import IStrategicPlanner
from releases.cognitive_os.core.models.cognitive import PlanHypothesis


class _GoalDecomposer:
    """Internal goal analysis and DAG generation."""

    @staticmethod
    def parse_steps(goal: str, constraints: dict) -> List[Dict[str, Any]]:
        """Extract steps from goal text and constraints."""
        import re
        tokens = re.sub(r'[,.!?;:]+', ' ', goal.lower()).split()
        steps: List[Dict[str, Any]] = []
        suggested = {
            "build": {"action": "build", "tool": "builder", "deps": []},
            "deploy": {"action": "deploy", "tool": "deployer", "deps": ["build"]},
            "test": {"action": "test", "tool": "tester", "deps": ["build"]},
            "analyze": {"action": "analyze", "tool": "analyzer", "deps": []},
            "review": {"action": "review", "tool": "reviewer", "deps": ["analyze"]},
            "plan": {"action": "plan", "tool": "planner", "deps": []},
            "install": {"action": "install", "tool": "installer", "deps": []},
            "configure": {"action": "configure", "tool": "configurator", "deps": ["install"]},
        }
        for token in tokens:
            if token in suggested and not any(s["action"] == token for s in steps):
                steps.append(dict(suggested[token]))
        if not steps and constraints:
            steps = [{"action": "execute", "tool": "executor", "deps": []}]
        if not steps:
            steps = [{"action": "process", "tool": "processor", "deps": []}]
        if constraints.get("parallel"):
            for i, s in enumerate(steps):
                if i > 0 and not s["deps"]:
                    s["parallel"] = True
        return steps

    @staticmethod
    def build_dag(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        nodes = [{"id": s["action"], "tool": s["tool"], "parallel": s.get("parallel", False)} for s in steps]
        edges = []
        for s in steps:
            for dep in s.get("deps", []):
                if any(n["id"] == dep for n in nodes):
                    edges.append({"from": dep, "to": s["action"]})
        return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}

    @staticmethod
    def estimate_resources(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "estimated_steps": len(steps),
            "parallelizable": sum(1 for s in steps if s.get("parallel", False)),
            "tools_needed": list({s["tool"] for s in steps}),
        }

    @staticmethod
    def compute_confidence(steps: List[Dict[str, Any]], constraints: dict) -> float:
        score = 0.3 if steps else 0.0
        if len(steps) >= 2:
            score += 0.2
        if constraints:
            score += 0.2
        has_deps = any(s.get("deps") for s in steps)
        if has_deps:
            score += 0.15
        if any(s.get("tool") for s in steps):
            score += 0.15
        return min(max(score, 0.1), 1.0)


class StrategicPlanner(IStrategicPlanner):
    """Decomposes goals into structured DAG plans.

    LAW-6: every public method requires tenant_id.
    """

    def __init__(self) -> None:
        self._plans: Dict[str, PlanHypothesis] = {}

    def decompose_goal(
        self,
        goal: str,
        tenant_id: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> PlanHypothesis:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not goal:
            raise ValueError("goal is required")
        constraints = constraints or {}
        steps = _GoalDecomposer.parse_steps(goal, constraints)
        dag = _GoalDecomposer.build_dag(steps)
        resources = _GoalDecomposer.estimate_resources(steps)
        confidence = _GoalDecomposer.compute_confidence(steps, constraints)
        hypothesis_id = f"hyp-{uuid.uuid4().hex[:16]}"
        sig = hashlib.sha256(
            json.dumps(dag, sort_keys=True).encode()
        ).hexdigest()[:32]
        hypothesis = PlanHypothesis(
            hypothesis_id=hypothesis_id,
            tenant_id=tenant_id,
            goal_id=f"goal-{uuid.uuid4().hex[:12]}",
            dag_blueprint={"dag": dag, "resource_profile": resources, "goal": goal},
            confidence_score=confidence,
            validator_signature=sig,
        )
        self._plans[hypothesis_id] = hypothesis
        return hypothesis

    def evaluate_feasibility(
        self,
        plan: Dict[str, Any],
        tenant_id: str,
    ) -> bool:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        dag = plan.get("dag", plan)
        nodes = dag.get("nodes", [])
        edges = dag.get("edges", [])
        if not nodes:
            return False
        node_ids = {n["id"] for n in nodes}
        for e in edges:
            if e["from"] not in node_ids or e["to"] not in node_ids:
                return False
        from collections import Counter
        in_degree: Dict[str, int] = Counter()
        for e in edges:
            in_degree[e["to"]] += 1
        if edges:
            has_source = any(in_degree.get(nid, 0) == 0 for nid in node_ids)
            if not has_source:
                return False  # cycle detected (no node with zero in-degree)
        return True

    def list_active_plans(
        self,
        tenant_id: str,
        project_id: str = "",
        limit: int = 10,
    ) -> List[str]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        results: List[str] = []
        for hyp in self._plans.values():
            if hyp.tenant_id != tenant_id:
                continue
            if project_id and hyp.project_id and hyp.project_id != project_id:
                continue
            results.append(hyp.hypothesis_id)
        return results[:limit]

    def get_plan(
        self,
        hypothesis_id: str,
        tenant_id: str,
    ) -> PlanHypothesis:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        hyp = self._plans.get(hypothesis_id)
        if not hyp or hyp.tenant_id != tenant_id:
            raise KeyError(f"Plan not found: {hypothesis_id}")
        return hyp
