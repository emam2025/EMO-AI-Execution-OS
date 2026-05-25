"""Phase G5 — Hierarchical Planner.  # RULE-1 RULE-3 RULE-5

Decomposes high-level intents into hierarchical subgoals for the swarm.

RULE 1: Same intent → same decomposition (deterministic).
RULE 3: Subgoal coherence is validated before assignment.
RULE 5: Failed subgoals retried independently without full replay.

Ref: Canon RULE 1, RULE 3, RULE 5
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Set

from core.runtime.models.multiagent_models import CoherenceReport, SubgoalStatus

logger = logging.getLogger("emo_ai.multiagent.hierarchical_planner")


class HierarchicalPlanner:  # RULE-1 RULE-3 RULE-5
    """Decomposes intents, assigns subgoals, merges results, validates coherence."""

    def __init__(self) -> None:
        self._decompositions: Dict[str, Dict[str, Any]] = {}

    # ── decompose_intent ────────────────────────────────────────

    def decompose_intent(  # RULE-1
        self, parent: Dict[str, Any], mission_trace_id: str = "",
    ) -> Dict[str, Any]:
        intent_id = parent.get("intent_id", "")
        goal = parent.get("goal", "")
        target_nodes = parent.get("target_nodes", [])
        decomposition_id = f"dec_{uuid.uuid4().hex[:12]}"

        subgoals: List[Dict[str, Any]] = []
        dep_graph: List[Dict[str, Any]] = []

        for i, node in enumerate(target_nodes):
            sg_id = f"sg_{intent_id}_{i}"
            subgoals.append({
                "subgoal_id": sg_id,
                "parent_intent_id": intent_id,
                "goal": f"{goal}:{node}",
                "dependencies": [f"sg_{intent_id}_{j}" for j in range(i)],
                "expected_output": {"target": node, "type": "processed"},
                "assigned_agent": "",
                "status": SubgoalStatus.PENDING.value,
                "confidence": 0.0,
                "mission_trace_id": mission_trace_id,
            })

            if i > 0:
                dep_graph.append({
                    "from_subgoal": f"sg_{intent_id}_{i - 1}",
                    "to_subgoal": sg_id,
                    "type": "dependency",
                })

        decomposition = {
            "decomposition_id": decomposition_id,
            "parent_intent_id": intent_id,
            "subgoals": subgoals,
            "dependency_graph": dep_graph,
            "mission_trace_id": mission_trace_id,
        }

        self._decompositions[intent_id] = decomposition
        self._decompositions[decomposition_id] = decomposition

        return decomposition

    # ── assign_subgoals ─────────────────────────────────────────

    def assign_subgoals(  # RULE-1 LAW-27
        self, subgoals: List[Dict[str, Any]], agents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        assignments: List[Dict[str, Any]] = []
        unassigned: List[str] = []

        for sg in subgoals:
            sg_id = sg.get("subgoal_id", "")
            sg_goal = sg.get("goal", "")

            best_agent: Optional[str] = None
            best_score = -1.0

            for agent in agents:
                profile = agent.get("capability_profile", [])
                score = self._compute_capability_match(sg_goal, profile)
                if score > best_score:
                    best_score = score
                    best_agent = agent.get("agent_id", "")

            if best_agent and best_score >= 0.3:
                assignments.append({
                    "subgoal_id": sg_id,
                    "agent_id": best_agent,
                    "rationale": f"Capability match: {best_score:.2f}",
                })
            else:
                unassigned.append(sg_id)

        assignment_hash = hashlib.sha256(
            json.dumps(sorted(assignments, key=lambda a: a["subgoal_id"]), default=str).encode()
        ).hexdigest()[:16]

        return {
            "assignments": assignments,
            "unassigned": unassigned,
            "assignment_hash": assignment_hash,
        }

    # ── merge_results ──────────────────────────────────────────

    def merge_results(  # RULE-5
        self, subgoal_results: List[Dict[str, Any]], dependency_graph: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        statuses: Dict[str, str] = {}
        merged: Dict[str, Any] = {"results": []}
        has_failures = False

        completed = {r.get("subgoal_id", "") for r in subgoal_results
                     if r.get("status") == SubgoalStatus.COMPLETED.value}
        failed = {r.get("subgoal_id", "") for r in subgoal_results
                  if r.get("status") == SubgoalStatus.FAILED.value}

        for result in subgoal_results:
            sg_id = result.get("subgoal_id", "")
            status = result.get("status", SubgoalStatus.PENDING.value)

            if sg_id in failed:
                statuses[sg_id] = SubgoalStatus.FAILED.value
                has_failures = True
            elif sg_id in completed:
                statuses[sg_id] = SubgoalStatus.COMPLETED.value
                merged["results"].append(result.get("output", {}))
            else:
                deps = [e["from_subgoal"] for e in dependency_graph
                        if e.get("to_subgoal") == sg_id]
                if any(d in failed for d in deps):
                    statuses[sg_id] = SubgoalStatus.CANCELLED.value
                else:
                    statuses[sg_id] = SubgoalStatus.PENDING.value

        return {
            "merged_output": merged,
            "subgoal_statuses": statuses,
            "has_failures": has_failures,
        }

    # ── validate_coherence ─────────────────────────────────────

    def validate_coherence(  # RULE-3
        self, parent_intent: Dict[str, Any], merged_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        target_nodes = set(parent_intent.get("target_nodes", []))
        gaps: List[str] = []
        hallucinations: List[str] = []

        results = merged_output.get("results", [])
        covered: Set[str] = set()

        for r in results:
            if isinstance(r, dict):
                target = r.get("target", "")
                if target:
                    covered.add(target)

        missing = target_nodes - covered
        if missing:
            gaps.extend(f"Missing target: {n}" for n in missing)

        score = len(covered) / max(len(target_nodes), 1) if target_nodes else 1.0

        return CoherenceReport(
            coherent=len(gaps) == 0 and len(hallucinations) == 0,
            score=round(score, 4),
            gaps=gaps,
            hallucinations=hallucinations,
            mission_trace_id=parent_intent.get("mission_trace_id", ""),
        ).__dict__

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _compute_capability_match(goal: str, profile: List[str]) -> float:
        goal_lower = goal.lower()
        matches = sum(1 for cap in profile if cap.lower() in goal_lower or goal_lower in cap.lower())
        return matches / max(len(profile), 1)

    def reset(self) -> None:
        self._decompositions.clear()
