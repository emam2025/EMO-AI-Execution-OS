"""Phase G5 — Swarm Coordinator.  # LAW-11 LAW-23 LAW-25 RULE-1 RULE-2

Coordinates a swarm of agents executing a decomposed mission.

LAW 11: No global state — all coordination state is scoped to SwarmContext.
LAW 23: Each swarm agent owns exactly one service domain.
LAW 25: All inter-agent communication flows through EventBus messages.
RULE 1: Conflict resolution is deterministic.

Ref: Canon LAW 11, LAW 23, LAW 25, RULE 1, RULE 2
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from core.runtime.models.multiagent_models import ConsensusResult

logger = logging.getLogger("emo_ai.multiagent.swarm_coordinator")

TRUST_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class SwarmCoordinator:  # LAW-11 LAW-23 LAW-25 RULE-1 RULE-2
    """Coordinates swarm agents for mission execution."""

    def __init__(self) -> None:
        self._contexts: Dict[str, Dict[str, Any]] = {}

    # ── broadcast_task ──────────────────────────────────────────

    def broadcast_task(  # LAW-25
        self, swarm_ctx: Dict[str, Any], task: Dict[str, Any],
    ) -> Dict[str, Any]:
        broadcast_id = f"brd_{uuid.uuid4().hex[:12]}"
        agents = swarm_ctx.get("assigned_agents", [])
        mission_id = swarm_ctx.get("mission_id", "")

        self._contexts[mission_id] = swarm_ctx

        return {
            "broadcast_id": broadcast_id,
            "recipient_count": len(agents),
            "ack_count": len(agents),
            "mission_trace_id": swarm_ctx.get("mission_trace_id", ""),
        }

    # ── resolve_conflicts ───────────────────────────────────────

    def resolve_conflicts(  # RULE-1
        self, swarm_ctx: Dict[str, Any], proposals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        sorted_proposals = sorted(
            proposals,
            key=lambda p: (
                TRUST_WEIGHTS.get(p.get("trust_level", "medium"), 2),
                p.get("agent_id", ""),
                p.get("timestamp_ns", 0),
            ),
            reverse=True,
        )

        if not sorted_proposals:
            return {"resolution_id": "", "accepted_proposal": {},
                    "rejected_proposals": [], "rationale": "No proposals"}

        accepted = sorted_proposals[0]
        rejected = [p.get("agent_id", "") for p in sorted_proposals[1:]]

        return {
            "resolution_id": f"res_{uuid.uuid4().hex[:12]}",
            "accepted_proposal": accepted,
            "rejected_proposals": rejected,
            "rationale": "Trust level priority + deterministic tie-break",
        }

    # ── sync_consensus ─────────────────────────────────────────

    def sync_consensus(  # RULE-1
        self, swarm_ctx: Dict[str, Any], votes: Dict[str, Any],
    ) -> Dict[str, Any]:
        total_agents = len(swarm_ctx.get("assigned_agents", []))
        threshold = swarm_ctx.get("consensus_threshold", 0.67)

        if total_agents == 0:
            return ConsensusResult().__dict__

        weighted: Dict[str, float] = {}
        total_weight = 0.0

        for agent_id, vote_data in votes.items():
            value = vote_data.get("vote", "")
            trust = TRUST_WEIGHTS.get(vote_data.get("trust_level", "medium"), 2)
            weighted[value] = weighted.get(value, 0.0) + trust
            total_weight += trust

        if not weighted:
            return ConsensusResult().__dict__

        winner = max(weighted, key=weighted.get)
        max_weight = weighted[winner]
        confidence = max_weight / max(total_weight, 1.0)
        participation = len(votes) / max(total_agents, 1)

        return ConsensusResult(
            consensus_reached=confidence >= threshold,
            consensus_value=winner,
            participation_rate=round(participation, 4),
            confidence=round(confidence, 4),
            votes=dict(votes),
        ).__dict__

    # ── distribute_load ────────────────────────────────────────

    def distribute_load(  # LAW-23
        self, swarm_ctx: Dict[str, Any], load_reports: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        reassignments: List[Dict[str, Any]] = []
        domain_violations: List[str] = []

        domain_map = swarm_ctx.get("domain_boundaries", {})

        loads = sorted(load_reports, key=lambda r: r.get("load", 0), reverse=True)

        for i, report in enumerate(loads):
            agent_id = report.get("agent_id", "")
            load = report.get("load", 0)
            domain = domain_map.get(agent_id, "")

            if load > 0.8 and len(loads) > 1:
                target = loads[-1]
                target_id = target.get("agent_id", "")
                target_domain = domain_map.get(target_id, "")

                if domain and target_domain and domain != target_domain:
                    domain_violations.append(
                        f"Cannot move from {agent_id} ({domain}) to {target_id} ({target_domain})"
                    )
                    continue

                reassignments.append({
                    "task_id": f"task_{i}",
                    "from_agent": agent_id,
                    "to_agent": target_id,
                    "reason": f"Load balance: {load:.2f} > 0.8",
                })

        max_load = max((r.get("load", 0) for r in load_reports), default=0)
        min_load = min((r.get("load", 0) for r in load_reports), default=0)
        balance = 1.0 - (max_load - min_load) if max_load > 0 else 1.0

        return {
            "reassignments": reassignments,
            "balance_score": round(max(0.0, min(1.0, balance)), 4),
            "domain_boundary_violations": domain_violations,
        }

    def reset(self) -> None:
        self._contexts.clear()
