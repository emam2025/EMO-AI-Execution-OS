"""Phase G3 — Cost Optimizer.  # LAW-15 RULE-1

Concrete implementation of ICostOptimizer.

Estimates execution costs, detects resource waste, suggests tool
alternatives, and enforces budgets. All methods are deterministic.

Ref: Canon LAW 15 (Cost Limits), RULE 1 (Determinism)
Ref: artifacts/design/g3/protocols/01_optimizer_protocols.py
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional



logger = logging.getLogger("emo_ai.optimizer.cost_optimizer")

DEFAULT_BASELINE_COSTS: Dict[str, float] = {
    "search": 0.5,
    "analyze": 0.8,
    "summarize": 0.3,
    "fetch": 0.4,
    "transform": 0.6,
    "default": 1.0,
}


class CostOptimizer:  # LAW-15 RULE-1
    """Estimates and enforces execution cost budgets.

    All cost functions are deterministic — same inputs always produce
    the same estimates.
    """

    def estimate_execution_cost(  # LAW-15
        self,
        nodes: List[Dict[str, Any]],
        baseline_costs: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        costs = baseline_costs or dict(DEFAULT_BASELINE_COSTS)
        total_cpu = 0.0
        total_mem = 0.0
        total_api = 0
        estimated_duration = 0.0

        for node in nodes:
            if isinstance(node, dict):
                tool = node.get("tool_name", "default")
                cpu = costs.get(tool, costs["default"])
                mem = costs.get(f"{tool}_mem", 100.0)
                api = 1

                total_cpu += cpu
                total_mem += mem
                total_api += api
                estimated_duration += cpu * 1000

        return {
            "total_cpu_seconds": round(total_cpu, 4),
            "total_memory_mb": round(total_mem, 2),
            "total_api_calls": total_api,
            "estimated_duration_ms": round(estimated_duration, 2),
        }

    def detect_resource_waste(  # LAW-15
        self,
        nodes: List[Dict[str, Any]],
        execution_trace: List[Dict[str, Any]],
        thresholds: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        thr = thresholds or {"cpu_waste_pct": 0.3, "mem_waste_pct": 0.3}
        waste: List[Dict[str, Any]] = []

        trace_map: Dict[str, float] = {}
        for span in execution_trace:
            if isinstance(span, dict):
                nid = span.get("node_id", "")
                dur = span.get("duration_ms", 0.0) or 0.0
                if nid:
                    trace_map[nid] = dur

        for node in nodes:
            if isinstance(node, dict):
                nid = node.get("node_id", "")
                actual = trace_map.get(nid, 0.0)
                estimated = node.get("estimated_cost", 0.0) * 1000
                if estimated > 0 and actual > 0 and actual < estimated * (1 - thr["cpu_waste_pct"]):
                    waste.append({
                        "node_id": nid,
                        "wasted_cpu": round(estimated - actual, 2),
                        "wasted_memory": 0.0,
                        "reason": f"Actual {actual:.0f}ms << estimated {estimated:.0f}ms",
                    })

        return waste

    def suggest_alternative_tools(  # RULE-1
        self,
        node: Dict[str, Any],
        tool_registry: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        alternatives: List[Dict[str, Any]] = []
        current_tool = node.get("tool_name", "")

        if not current_tool:
            return alternatives

        if tool_registry:
            for alt in tool_registry:
                if isinstance(alt, dict):
                    alt_name = alt.get("tool_name", "")
                    if alt_name and alt_name != current_tool:
                        alt_cost = alt.get("estimated_cost", 1.0)
                        alternatives.append({
                            "tool_name": alt_name,
                            "estimated_cost": alt_cost,
                            "estimated_latency": alt_cost * 1000,
                            "trade_offs": f"Cost {alt_cost:.2f} vs {DEFAULT_BASELINE_COSTS.get(current_tool, 1.0):.2f}",
                        })

        cheaper_base = DEFAULT_BASELINE_COSTS.get(current_tool, 1.0)
        for tool, cost in DEFAULT_BASELINE_COSTS.items():
            if tool != current_tool and cost < cheaper_base:
                alternatives.append({
                    "tool_name": tool,
                    "estimated_cost": cost,
                    "estimated_latency": cost * 1000,
                    "trade_offs": f"Cost {cost:.2f} vs {cheaper_base:.2f} ({(1 - cost/cheaper_base)*100:.0f}% cheaper)",
                })

        alternatives.sort(key=lambda a: a["estimated_cost"])
        return alternatives[:3]

    def enforce_budget(  # LAW-15
        self,
        estimated_cost: Dict[str, Any],
        budget: Dict[str, Any],
    ) -> Dict[str, Any]:
        exceeded: List[str] = []
        overage_pct = 0.0
        cpu = estimated_cost.get("total_cpu_seconds", 0.0)
        mem = estimated_cost.get("total_memory_mb", 0.0)
        api = estimated_cost.get("total_api_calls", 0)

        max_cpu = budget.get("max_cpu_seconds", float("inf"))
        max_mem = budget.get("max_memory_mb", float("inf"))
        max_api = budget.get("max_api_calls", float("inf"))

        if max_cpu < float("inf"):
            cpu_over = (cpu / max_cpu) - 1.0
            if cpu_over > 0:
                exceeded.append("cpu_seconds")
                overage_pct = max(overage_pct, cpu_over * 100)

        if max_mem < float("inf"):
            mem_over = (mem / max_mem) - 1.0
            if mem_over > 0:
                exceeded.append("memory_mb")
                overage_pct = max(overage_pct, mem_over * 100)

        if max_api < float("inf"):
            api_over = (api / max_api) - 1.0
            if api_over > 0:
                exceeded.append("api_calls")
                overage_pct = max(overage_pct, api_over * 100)

        return {
            "within_budget": len(exceeded) == 0,
            "exceeded_fields": exceeded,
            "overage_percent": round(overage_pct, 2),
            "recommended_actions": ["reduce_nodes"] if exceeded else [],
        }
