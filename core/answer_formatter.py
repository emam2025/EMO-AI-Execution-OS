"""Answer formatter — converts execution results to user-facing text.

Pure presentation logic. No coordination, no execution, no state.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .types import ExecutionPlan, Intent


class AnswerFormatter:
    """Formats DAG execution results into user-facing answers.

    One method per intent type. Easy to extend without touching the runtime.
    """

    @staticmethod
    def format(
        plan: ExecutionPlan, state: Dict[str, Any],
    ) -> str:
        intent = plan.intent
        target = plan.target

        if intent == Intent.HOTSPOTS:
            return AnswerFormatter._format_hotspots(state)
        if intent == Intent.IMPACT:
            return AnswerFormatter._agent_answer(state.get("agent", {}), target)
        if intent == Intent.WHY:
            return AnswerFormatter._agent_answer(state.get("agent", {}), target)
        if intent == Intent.REFACTOR:
            return AnswerFormatter._agent_answer(state.get("agent", {}), target)
        if intent == Intent.SEMANTIC:
            return AnswerFormatter._format_semantic(
                state.get("hybrid", {}), state.get("agent"),
                state.get("context"),
            )
        if intent in (Intent.EXPLAIN, Intent.EXPLORE, Intent.UNKNOWN):
            return AnswerFormatter._format_explain(
                state.get("agent", {}), target, state.get("context"),
            )

        return f"Analysis complete for '{target}' (intent: {intent})."

    @staticmethod
    def _format_explain(
        result: Dict[str, Any],
        target: Optional[str] = None,
        context_result: Optional[Dict[str, Any]] = None,
    ) -> str:
        parts: List[str] = []
        if context_result:
            sc = context_result.get("structured_context", {})
            llm_block = context_result.get("llm_ready_prompt_block", "")
            if llm_block:
                parts.append(llm_block)
            risk = sc.get("risk_analysis", [])
            if risk:
                high_risk = [
                    f"{r.get('symbol_name', '?')} (depth={r.get('depth', 0)})"
                    for r in risk if r.get("importance", 0) > 5
                ]
                if high_risk:
                    parts.append("Key risk symbols: " + ", ".join(high_risk[:3]))
        if result:
            insight = result.get("insight_summary")
            if insight:
                parts.append(insight)
            heuristic = result.get("heuristic_analysis", {})
            if isinstance(heuristic, dict):
                imp = heuristic.get("importance")
                risk = heuristic.get("overall_risk")
                if imp is not None:
                    parts.append(f"Importance score: {imp}")
                if risk:
                    parts.append(f"Overall risk: {risk}")
            conclusion = result.get("conclusion")
            if conclusion:
                parts.append(f"Conclusion: {conclusion}")
        if not parts:
            return AnswerFormatter._agent_answer(result, target)
        return "\n".join(parts)

    @staticmethod
    def empty(plan: ExecutionPlan) -> str:
        if plan.target and plan.target_type == "unknown":
            return (
                f"Symbol/file '{plan.target}' not found in the graph. "
                "Cannot proceed with the requested analysis."
            )
        if plan.target is None:
            return (
                "I could not determine what symbol or file you are asking about. "
                "Please specify a symbol name (e.g., 'explain export')."
            )
        return "Insufficient graph data to answer this query."

    # ── private ─────────────────────────────────────────────────────

    @staticmethod
    def _format_hotspots(state: Dict[str, Any]) -> str:
        hotspots = state.get("hotspots") or state.get("enrich", {})
        if isinstance(hotspots, dict):
            hs = hotspots.get("evidence", {}).get("hotspots", [])
        elif isinstance(hotspots, list):
            hs = hotspots
        else:
            hs = []
        if not hs:
            return "No hotspot data available."
        lines = [f"Top {len(hs)} hotspot(s):"]
        for i, h in enumerate(hs[:10], 1):
            lines.append(
                f"  {i}. {h.get('symbol_name', '?')} — "
                f"score={h.get('importance_score', 0)}, "
                f"calls={h.get('incoming_calls', 0)}, "
                f"role={h.get('role', '?')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _agent_answer(
        result: Dict[str, Any], target: Optional[str] = None,
    ) -> str:
        if not result:
            return f"No analysis available for '{target}'." if target else "No analysis available."
        parts: List[str] = []
        insight = result.get("insight_summary")
        if insight:
            parts.append(insight)
        heuristic = result.get("heuristic_analysis", {})
        if isinstance(heuristic, dict):
            imp = heuristic.get("importance")
            risk = heuristic.get("overall_risk")
            if imp is not None:
                parts.append(f"Importance score: {imp}")
            if risk:
                parts.append(f"Overall risk: {risk}")
            rb = heuristic.get("risk_breakdown", [])
            if rb:
                high_risks = [
                    f"{r['dimension']}={r['risk']}"
                    for r in rb if r.get("risk") in ("HIGH", "MEDIUM")
                ]
                if high_risks:
                    parts.append("Risks: " + "; ".join(high_risks))
        reasoning = result.get("reasoning", [])
        if isinstance(reasoning, list) and reasoning:
            parts.extend(reasoning[:5])
        conclusion = result.get("conclusion")
        if conclusion:
            parts.append(f"Conclusion: {conclusion}")
        if not parts:
            return f"Analysis complete for '{target}'." if target else "Analysis complete."
        return "\n".join(parts)

    @staticmethod
    def _format_semantic(
        hybrid_result: Dict[str, Any],
        explain_result: Optional[Dict[str, Any]] = None,
        context_result: Optional[Dict[str, Any]] = None,
    ) -> str:
        parts: List[str] = []
        merged = hybrid_result.get("merged_results", [])
        if not merged:
            error = hybrid_result.get("error")
            return error if error else "No results found."
        parts.append(f"Found {len(merged)} relevant symbol(s):")
        for i, h in enumerate(merged[:10], 1):
            parts.append(
                f"  {i}. {h.get('symbol_name', '?')} — "
                f"score={h.get('final_score', h.get('hybrid_score', 0))}, "
                f"role={h.get('role', '?')}, "
                f"risk={h.get('overall_risk', 'LOW')}"
            )
        notes = hybrid_result.get("improvement_notes", "")
        if notes:
            parts.append(f"\n{notes}")

        # ── Compiled context (from context_compiler.build_llm_context) ──
        if context_result:
            sc = context_result.get("structured_context", {})
            sym_ctx = sc.get("symbol_context", {})
            stats = sym_ctx.get("summary_stats", {})
            if stats:
                parts.append(
                    f"\n--- Context --- "
                    f"Incoming: {stats.get('incoming_calls', 0)}, "
                    f"Outgoing: {stats.get('outgoing_calls', 0)}, "
                    f"Importance: {stats.get('importance_score', 0)}"
                )
            graph_summary = sc.get("graph_summary", {})
            if graph_summary:
                parts.append(
                    f"Graph: {graph_summary.get('node_count', 0)} nodes, "
                    f"{graph_summary.get('edge_count', 0)} edges"
                )
            risk = sc.get("risk_analysis", [])
            if risk:
                high_risk = [
                    f"{r.get('symbol_name', '?')} (depth={r.get('depth', 0)})"
                    for r in risk if r.get("importance", 0) > 5
                ]
                if high_risk:
                    parts.append("Key risk symbols: " + ", ".join(high_risk[:3]))
            llm_block = context_result.get("llm_ready_prompt_block", "")
            if llm_block:
                parts.append(f"\n{llm_block}")

        if explain_result:
            insight = explain_result.get("insight_summary")
            if insight:
                parts.append(f"\nExplanation: {insight}")
            conclusion = explain_result.get("conclusion")
            if conclusion:
                parts.append(f"\nConclusion: {conclusion}")
        formula = hybrid_result.get("formula", "")
        if formula:
            parts.append(f"\nScoring: {formula}")
        return "\n".join(parts)
