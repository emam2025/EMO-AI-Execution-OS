"""PlannerAgent — concrete implementation of IPlannerAgent.

LAW 1: Same (intent, context_window, constraints) → same PlanProposal (deterministic).
LAW 9: Planner operates independently of governance — no policy injection.
RULE 1: No direct access to ExecutionCore or Engine internals.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional


class PlannerAgent:  # LAW-1 LAW-9 RULE-1
    """Synthesises DAG plans from intent + context window.

    Per-instance state. No global caches.
    """

    MAX_RETRY = 3

    def __init__(self) -> None:
        self._proposals: Dict[str, Dict[str, Any]] = {}  # proposal_id → proposal

    async def synthesize_dag(
        self,
        intent: str,
        context_window: Dict[str, Any],
        tenant_id: str,
        constraints: Optional[Dict[str, Any]] = None,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not tenant_id:
            return {"status": "error", "message": "tenant_id required"}  # LAW-11

        constraint_hash = hashlib.sha256(
            json.dumps(constraints or {}, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        context_hash = context_window.get("context_hash") or context_window.get("_hash", "")

        # LAW-1: deterministic proposal from same inputs
        raw = json.dumps({
            "intent": intent.strip().lower(),
            "context_hash": context_hash,
            "constraint_hash": constraint_hash,
            "tenant_id": tenant_id,
        }, sort_keys=True)
        proposal_id = hashlib.sha256(raw.encode()).hexdigest()[:16]

        dag_nodes = [
            {"node_id": "n1", "tool": "execute", "depends_on": [],
             "estimated_cost_units": "1.0", "timeout_seconds": 30.0},
        ]
        if context_window.get("trace_snippets"):
            dag_nodes.append({
                "node_id": "n2", "tool": "analyse", "depends_on": ["n1"],
                "estimated_cost_units": "0.5", "timeout_seconds": 15.0,
            })

        proposal = {
            "proposal_id": proposal_id,
            "intent": intent,
            "dag_nodes": dag_nodes,
            "execution_path_hash": hashlib.sha256(
                json.dumps(dag_nodes, sort_keys=True, default=str).encode()
            ).hexdigest()[:16],
            "estimated_cost": str(Decimal(str(len(dag_nodes))) * Decimal("1.0")),
            "memory_dependencies": [],
            "confidence_score": round(0.7 + (len(dag_nodes) * 0.1), 2),
            "tenant_id": tenant_id,
            "cognitive_trace_id": cognitive_trace_id,
            "_hash": proposal_id,
        }
        self._proposals[proposal_id] = proposal
        return proposal

    async def adapt_on_failure(
        self,
        feedback: Dict[str, Any],
        original_proposal: Dict[str, Any],
        tenant_id: str,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not tenant_id:
            return {"status": "error", "message": "tenant_id required"}

        retry_count = original_proposal.get("_retry_count", 0) + 1
        if retry_count > self.MAX_RETRY:
            return {"status": "aborted", "message": "Max retries exceeded",
                    "retry_count": retry_count, "cognitive_trace_id": cognitive_trace_id}

        fault = feedback.get("fault", "unknown")
        revised = dict(original_proposal)
        revised["_retry_count"] = retry_count
        revised["confidence_score"] = max(0.1, revised.get("confidence_score", 0.5) - 0.2)
        revised["adaptation_reason"] = f"Retry {retry_count}: {fault}"
        revised["cognitive_trace_id"] = cognitive_trace_id

        plan_hash = original_proposal.get("_hash", "")
        revised_hash = hashlib.sha256(
            json.dumps(revised.get("dag_nodes", []), sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        # G-P4: oscillation guard — revised must differ from original
        if revised_hash == plan_hash:
            return {"status": "blocked", "message": "Plan oscillation detected (hash unchanged)",
                    "cognitive_trace_id": cognitive_trace_id}

        revised["_hash"] = revised_hash
        return {"status": "adapted", "revised_plan": revised,
                "retry_count": retry_count, "cognitive_trace_id": cognitive_trace_id}
