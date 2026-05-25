"""Phase G1 — DAGSynthesizer implementation.  # RULE-1

Synthesizes ExecutionPlan DAGs from structured swarming results.
All results are deterministic given the same input.

Ref: Canon RULE 1 (Determinism)
Ref: artifacts/design/g1/02_models.md §2
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.runtime.models.planning_models import (
    ExecutionPlan,
    SwarmIntent,
    PlanNode,
)

logger = logging.getLogger("emo_ai.orchestration.dag_synthesizer")


class DAGSynthesizer:  # RULE-1
    """Synthesizes ExecutionPlan DAGs from SwarmIntents.

    Each intent maps to an ordered list of PlanNodes with derived
    dependencies, forming a deterministic execution DAG.

    All methods are pure functions of their inputs (no randomness,
    no external state).
    """

    def synthesize(  # RULE-1
        self,
        plan: ExecutionPlan,
        intents: List[SwarmIntent],
    ) -> ExecutionPlan:
        nodes: List[PlanNode] = []
        edges: List[Dict[str, Any]] = []

        # Merge top-N intents by confidence into DAG nodes
        scored = sorted(
            intents,
            key=lambda i: i.confidence if i.confidence is not None else 0.0,
            reverse=True,
        )

        seen: set = set()
        for idx, intent in enumerate(scored):
            if intent.tool_name in seen:
                continue
            seen.add(intent.tool_name)
            node = PlanNode(
                node_id=f"n{idx + 1}",
                tool_name=intent.tool_name,
                tool_params=dict(intent.parameters or {}),
                priority=intent.priority or 0,
                weight=intent.weight or 1.0,
            )
            nodes.append(node)

        for i, node in enumerate(nodes):
            for dep in nodes[:i]:
                if node.tool_name.startswith(dep.tool_name.split("_")[0]):
                    edges.append({
                        "from": dep.node_id,
                        "to": node.node_id,
                    })

        plan.dag_topology = edges
        return plan

    def validate(  # LAW-3
        self,
        plan: ExecutionPlan,
    ) -> bool:
        dag = plan.dag_topology or []
        node_ids = set()
        for node in plan.nodes or []:
            node_ids.add(node.node_id)
        for edge in dag:
            if edge.get("from") not in node_ids:
                return False
            if edge.get("to") not in node_ids:
                return False
        return True

    def reset(self) -> None:
        pass
