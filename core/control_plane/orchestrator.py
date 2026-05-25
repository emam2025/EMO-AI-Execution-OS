"""6.3 — ExecutionOrchestrator: global decision engine.

NOT a scheduler. NOT a queue manager.
This is the BRAIN that decides WHERE and WHY to execute a task.

Decision signals:
  - CPU load on each node
  - Network latency
  - Node reliability (historical failure rate)
  - Data locality (where data for this task lives)
  - Execution cost (estimated resource usage)
  - Affinity (prefer same node for related tasks)

The orchestrator SCORES each eligible node and picks the best one.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.control_plane.state.system_state import SystemStateBrain
from core.security.capabilities import TrustLevel

logger = logging.getLogger("emo_ai.control_plane.orchestrator")


@dataclass
class NodeScore:
    """Score for a single node."""
    node_id: str
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)


class ExecutionOrchestrator:
    """Global decision engine for execution placement.

    Decides which node should execute a given task based on
    multiple signals. Does NOT execute — it decides.
    """

    def __init__(self):
        self._decision_history: List[Dict[str, Any]] = []

    def select_node(
        self,
        task: Dict[str, Any],
        state: SystemStateBrain,
        preferred_nodes: Optional[List[str]] = None,
    ) -> str:
        """Select the best node for a task.

        Args:
            task: Task metadata (dag_id, tool, estimated_cost, etc.)
            state: Current system state (truth model).
            preferred_nodes: Optional list of preferred node IDs.

        Returns:
            The selected node_id.

        Raises:
            RuntimeError: If no suitable node is available.
        """
        candidates = self._score_nodes(task, state, preferred_nodes)

        if not candidates:
            raise RuntimeError("No suitable node available for task")

        candidates.sort(key=lambda ns: ns.score, reverse=True)
        best = candidates[0]

        decision = {
            "timestamp": time.time(),
            "task": task,
            "candidates": [(c.node_id, c.score, c.reasons) for c in candidates[:3]],
            "selected": best.node_id,
        }
        self._decision_history.append(decision)

        logger.info(
            "Orchestrator: '%s' → %s (score=%.2f, candidates=%d)",
            task.get("dag_id", "?"), best.node_id, best.score, len(candidates),
        )
        return best.node_id

    def _score_nodes(
        self,
        task: Dict[str, Any],
        state: SystemStateBrain,
        preferred: Optional[List[str]] = None,
    ) -> List[NodeScore]:
        """Score all eligible nodes and return ranked list."""
        preferred = preferred or []
        scores: List[NodeScore] = []
        all_nodes = state.healthy_nodes()

        for node in all_nodes:
            nid = node.node_id
            node_scores = {}
            reasons = []

            # Signal 1: CPU load (lower is better)
            metrics = state.get_load_metrics(nid)
            cpu = metrics.cpu_avg if metrics else 0.5
            cpu_score = max(0.0, 1.0 - cpu)
            node_scores["cpu"] = cpu_score * 30
            if cpu > 0.8:
                reasons.append(f"high_cpu({cpu:.2f})")
            elif cpu < 0.3:
                reasons.append(f"low_cpu({cpu:.2f})")

            # Signal 2: Error rate (lower is better)
            err = metrics.error_rate if metrics else 0.0
            err_score = max(0.0, 1.0 - err * 10)
            node_scores["error_rate"] = err_score * 20
            if err > 0.05:
                reasons.append(f"high_error({err:.3f})")

            # Signal 3: Latency (lower is better)
            latency = node.latency_ms
            lat_score = max(0.0, 1.0 - (latency / 500.0))
            node_scores["latency"] = lat_score * 15
            if latency > 100:
                reasons.append(f"high_latency({latency:.0f}ms)")

            # Signal 4: Worker availability (more = better)
            worker_count = len(state.workers_by_node(nid))
            worker_cap = sum(
                w.capacity - w.active_tasks
                for w in state.workers_by_node(nid)
            )
            avail_score = min(1.0, worker_cap / 10.0)
            node_scores["worker_avail"] = avail_score * 20
            if worker_cap > 0:
                reasons.append(f"workers_avail({worker_cap})")
            else:
                reasons.append("no_capacity")

            # Signal 5: Preference boost
            if nid in preferred:
                node_scores["preference"] = 15
                reasons.append("preferred")

            # Signal 6: Failure cluster penalty
            clusters = state.failure_clusters()
            penalty = 0
            for cid, fc in clusters.items():
                if nid in fc.nodes and fc.count > 3:
                    penalty += 20
            node_scores["failure_penalty"] = -penalty
            if penalty:
                reasons.append(f"failure_cluster(-{penalty})")

            # Signal 7: Trust level (E4)
            workers_on_node = state.workers_by_node(nid)
            min_trust = min(
                (w.trust_level for w in workers_on_node),
                default=TrustLevel.UNVERIFIED,
            )
            if min_trust == TrustLevel.TRUSTED:
                node_scores["trust"] = 10
                reasons.append("trusted")
            elif min_trust == TrustLevel.REMOTE:
                node_scores["trust"] = 5
                reasons.append("remote")
            else:
                node_scores["trust"] = 0
                reasons.append("unverified")

            total = sum(node_scores.values())
            scores.append(NodeScore(node_id=nid, score=total, reasons=reasons[:3]))

        return scores

    def select_worker(
        self,
        node_id: str,
        task: Dict[str, Any],
        state: SystemStateBrain,
    ) -> str:
        """Select the best worker on a specific node.

        Picks the most trusted, least-loaded worker on the selected node.
        """
        workers = state.workers_by_node(node_id)
        if not workers:
            raise RuntimeError(f"No workers on node {node_id}")

        # Sort by trust level (TRUSTED first), then by load
        trust_rank = {
            TrustLevel.TRUSTED: 0,
            TrustLevel.REMOTE: 1,
            TrustLevel.UNVERIFIED: 2,
        }
        workers.sort(key=lambda w: (trust_rank.get(w.trust_level, 99), w.active_tasks))
        best = workers[0]

        logger.debug(
            "Orchestrator: worker '%s' on node %s (trust=%s, tasks=%d/%d)",
            best.worker_id, node_id, best.trust_level.value, best.active_tasks, best.capacity,
        )
        return best.worker_id

    def decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent orchestration decisions."""
        return self._decision_history[-limit:]
