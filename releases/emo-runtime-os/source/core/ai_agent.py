"""Code Intelligence Agent – Phase 8 (Graph-first Retrieval + Heuristics).

Read-only reasoning layer over GraphRetrievalEngine.  Every response
includes standardised heuristic analysis and is backed by graph evidence.

Constraints:
    - No SQL            - No AST parsing      - No embeddings
    - Read-only via GraphRetrievalEngine
    - Every conclusion traceable to graph evidence
    - Insufficient data → "insufficient graph data"
"""

from typing import Any, Dict, List

from .graph_query import GraphQuery
from .ai_context_engine import AIContextEngine
from .graph_retrieval import GraphRetrievalEngine, SmartFilter


class CodeIntelligenceAgent:
    """Graph-first code intelligence agent.

    Usage:
        agent = CodeIntelligenceAgent(graph_query, ai_context)
        result = agent.explain("42")
    """

    def __init__(self, gq: GraphQuery, ctx: AIContextEngine):
        self.retrieval = GraphRetrievalEngine(gq, ctx)
        self.filter = SmartFilter()
        self.gq = gq
        self.ctx = ctx

    # ── public methods ──────────────────────────────────────────────────

    def explain(self, symbol_id: str) -> Dict[str, Any]:
        """Full explanation with heuristic analysis."""
        try:
            core = self.retrieval.retrieve_symbol_core(symbol_id)
        except LookupError:
            return self._empty("Symbol not found in graph")

        meta = core["meta"]
        sa = core["static_analysis"]
        name = meta.get("name", symbol_id)

        callers = self.retrieval.retrieve_callers(symbol_id)
        callees = self.retrieval.retrieve_callees(symbol_id)

        t2 = self.gq.traverse_depth(symbol_id, depth=2)
        n1 = len([n for n in t2.get("nodes", []) if n.get("depth") == 1])
        n2 = len([n for n in t2.get("nodes", []) if n.get("depth") == 2])

        incoming = sum(c.get("call_count", 1) for c in callers)
        outgoing = len(callees)

        heuristic = self.retrieval.heuristic_analysis(
            symbol_id, incoming=incoming, outgoing=outgoing, depth=2,
        )

        role = sa.get("role", "unknown")
        behaviour = sa.get("behavior", {})
        complexity = sa.get("complexity", {})

        if not callers and not callees:
            insight = f"'{name}' is a {role} with no graph neighbours"
        else:
            insight = (
                f"'{name}' is a {role} — "
                f"{len(callers)} caller(s) ({incoming} call(s)), "
                f"{len(callees)} callee(s), "
                f"cyclomatic={complexity.get('cyclomatic', 1)}, "
                f"importance={heuristic.get('importance', 0)}"
            )

        return self._result(
            insight=insight,
            evidence={
                "name": name,
                "type": meta.get("symbol_type"),
                "signature": meta.get("signature"),
                "file_id": meta.get("file_id"),
                "static_analysis": {
                    "role": role,
                    "is_async": behaviour.get("is_async"),
                    "is_recursive": behaviour.get("is_recursive"),
                    "cyclomatic": complexity.get("cyclomatic", 1),
                },
                "callers": [
                    {"symbol": c["symbol_name"], "call_count": c["call_count"]}
                    for c in callers
                ],
                "callees": [
                    {"symbol": c["symbol_name"], "edge_type": c.get("edge_type")}
                    for c in callees
                ],
                "graph_radius": {"depth_1": n1, "depth_2": n2},
            },
            heuristic=heuristic,
            conclusion=self._build_conclusion(heuristic, name, role),
        )

    def impact(self, target: str) -> Dict[str, Any]:
        """Impact analysis – accepts symbol_id or file_id."""
        meta = self.gq.get_symbol_metadata(target)
        if meta:
            return self._impact_symbol(target, meta)
        fmeta = self.gq.get_file_metadata(target)
        if fmeta:
            return self._impact_file(target, fmeta)
        return self._empty(f"'{target}' is neither a known symbol nor file")

    def top_hotspots(self, limit: int = 10) -> Dict[str, Any]:
        """Hotspots ranked by the standardised importance formula."""
        hotspots = self.retrieval.ranked_hotspots(limit=limit)
        if not hotspots:
            return self._empty("No symbols found with importance > 0")

        _, overall_risk = self._hotspot_risk(hotspots)

        insight = (
            f"Top {len(hotspots)} hotspot(s) ranked by importance score. "
            f"Highest: '{hotspots[0]['symbol_name']}' "
            f"(score={hotspots[0]['importance_score']})"
        )

        return self._result(
            insight=insight,
            evidence={"hotspots": hotspots},
            heuristic={
                "importance_formula": self.retrieval.ranker.IMPORTANCE_FORMULA,
                "top_score": hotspots[0]["importance_score"],
                "overall_project_risk": overall_risk,
                "hotspot_count": len(hotspots),
            },
            conclusion=(
                f"Symbol with highest impact: '{hotspots[0]['symbol_name']}' "
                f"({hotspots[0]['incoming_calls']} callers, "
                f"score={hotspots[0]['importance_score']}). "
                f"Project risk: {overall_risk}."
            ),
        )

    def why(self, symbol_id: str) -> Dict[str, Any]:
        """Explain why a symbol matters via centrality + heuristics."""
        try:
            core = self.retrieval.retrieve_symbol_core(symbol_id)
        except LookupError:
            return self._empty("Symbol not found")
        meta = core["meta"]
        name = meta.get("name", symbol_id)

        callers = self.retrieval.retrieve_callers(symbol_id)
        callees = self.retrieval.retrieve_callees(symbol_id)
        incoming = sum(c.get("call_count", 1) for c in callers)
        outgoing = len(callees)

        heuristic = self.retrieval.heuristic_analysis(
            symbol_id, incoming=incoming, outgoing=outgoing, depth=2,
        )
        importance = heuristic.get("importance", 0)

        central_factors: List[str] = []
        if incoming >= 5:
            central_factors.append(
                f"High fan-in ({incoming} incoming) — central API"
            )
        elif incoming >= 2:
            central_factors.append(f"Moderate fan-in ({incoming} incoming)")
        outgoing_risk = self.retrieval.ranker.fan_out_risk(outgoing)
        if outgoing_risk == "HIGH":
            central_factors.append(
                f"High fan-out ({outgoing} callees) — possible orchestrator"
            )
        if incoming >= 2 or outgoing >= 4:
            central_factors.append(
                f"Importance score = {importance} "
                f"(formula: {self.retrieval.ranker.IMPORTANCE_FORMULA})"
            )
        if not central_factors:
            central_factors.append("Low graph centrality — minimal impact")

        insight = (
            f"'{name}' importance = {importance}. "
            f"{central_factors[0]}"
        )

        return self._result(
            insight=insight,
            evidence={
                "name": name,
                "importance_score": importance,
                "incoming_calls": incoming,
                "outgoing_calls": outgoing,
                "callers": [{"symbol": c["symbol_name"], "calls": c["call_count"]} for c in callers],
                "callees": [{"symbol": c["symbol_name"]} for c in callees],
            },
            heuristic=heuristic,
            conclusion=(
                f"'{name}' is a {'critical' if importance >= 10 else 'significant' if importance >= 5 else 'low-impact'} "
                f"symbol (score={importance}). "
                f"{'Prioritise in code review.' if importance >= 5 else 'No special focus required.'}"
            ),
        )

    def suggest_refactor(self, symbol_id: str) -> Dict[str, Any]:
        """Evidence-based refactoring suggestions with heuristic analysis."""
        try:
            core = self.retrieval.retrieve_symbol_core(symbol_id)
        except LookupError:
            return self._empty("Symbol not found")
        meta = core["meta"]
        sa = core["static_analysis"]
        name = meta.get("name", symbol_id)

        callers = self.retrieval.retrieve_callers(symbol_id)
        callees = self.retrieval.retrieve_callees(symbol_id)
        incoming = sum(c.get("call_count", 1) for c in callers)
        outgoing = len(callees)

        heuristic = self.retrieval.heuristic_analysis(
            symbol_id, incoming=incoming, outgoing=outgoing, depth=2,
        )

        suggestions: List[Dict[str, Any]] = []

        if incoming >= 5:
            suggestions.append({
                "type": "bottleneck",
                "severity": "HIGH",
                "evidence": f"{incoming} incoming callers",
                "suggestion": "Extract interface / facade to decouple dependents",
            })
        if outgoing >= 8:
            suggestions.append({
                "type": "wide_scope",
                "severity": "MEDIUM",
                "evidence": f"{outgoing} different callees",
                "suggestion": "Split into smaller focused helpers",
            })
        cyclomatic = sa.get("complexity", {}).get("cyclomatic", 1)
        if cyclomatic > 7:
            suggestions.append({
                "type": "high_complexity",
                "severity": "HIGH",
                "evidence": f"cyclomatic complexity = {cyclomatic}",
                "suggestion": "Extract conditional branches into separate functions",
            })
        elif cyclomatic > 4:
            suggestions.append({
                "type": "moderate_complexity",
                "severity": "MEDIUM",
                "evidence": f"cyclomatic complexity = {cyclomatic}",
                "suggestion": "Simplify most complex branches",
            })
        if sa.get("behavior", {}).get("is_recursive"):
            suggestions.append({
                "type": "recursion",
                "severity": "LOW",
                "evidence": "function is recursive",
                "suggestion": "Add depth guard or convert to iterative",
            })
        if not suggestions:
            suggestions.append({
                "type": "clean",
                "severity": "NONE",
                "evidence": "all metrics within healthy ranges",
                "suggestion": "No refactoring warranted from graph data",
            })

        actionable = [s for s in suggestions if s["severity"] in ("HIGH", "MEDIUM")]

        return self._result(
            insight=(
                f"{len(actionable)} actionable suggestion(s) for '{name}'"
                if actionable else f"No refactoring needed for '{name}'"
            ),
            evidence={
                "name": name,
                "incoming_calls": incoming,
                "outgoing_calls": outgoing,
                "cyclomatic": cyclomatic,
                "is_recursive": sa.get("behavior", {}).get("is_recursive"),
                "role": sa.get("role"),
                "suggestions": suggestions,
            },
            heuristic=heuristic,
            conclusion=(
                suggestions[0]["suggestion"]
                if suggestions else "Insufficient graph data for suggestions"
            ),
        )

    # ── internal: impact helpers ────────────────────────────────────────

    def _impact_symbol(self, symbol_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        name = meta.get("name", symbol_id)
        try:
            chain = self.retrieval.retrieve_impact_chain(symbol_id, max_depth=3)
        except LookupError:
            return self._empty("Symbol not found")

        direct = chain.get("direct_impact", [])
        transitive = chain.get("transitive_impact", [])
        overall_risk = chain.get("overall_risk", "LOW")
        depth = chain.get("max_depth_reached", 0)

        callers = self.retrieval.retrieve_callers(symbol_id)
        incoming = sum(c.get("call_count", 1) for c in callers)

        heuristic = self.retrieval.heuristic_analysis(
            symbol_id, incoming=incoming, depth=depth,
        )

        insight = (
            f"Changing '{name}' impacts {len(direct)} direct caller(s) "
            f"and {len(transitive)} transitive symbol(s). "
            f"Risk: {overall_risk}."
        )

        return self._result(
            insight=insight,
            evidence={
                "target": {
                    "symbol_id": symbol_id,
                    "name": name,
                    "file_id": meta.get("file_id"),
                    "role": meta.get("properties", {}).get("role"),
                },
                "impact_summary": {
                    "direct_callers": len(direct),
                    "transitive_symbols": len(transitive),
                    "total_impacted": chain.get("total_impacted", 0),
                    "max_depth": depth,
                    "overall_risk": overall_risk,
                },
                "direct_impact": direct[:10],
                "transitive_impact": transitive[:10],
            },
            heuristic=heuristic,
            conclusion=(
                f"Risk level is {overall_risk}. "
                f"Review {len(direct)} direct caller(s) and "
                f"regression-test {len(transitive)} transitive path(s)."
                if overall_risk != "LOW"
                else f"Low risk — {len(direct)} direct caller(s) to verify."
            ),
        )

    def _impact_file(self, file_id: str, fmeta: Dict[str, Any]) -> Dict[str, Any]:
        impact_data = self.gq.impact_analysis(file_id)
        roots = impact_data.get("root_symbols", [])
        impacted = impact_data.get("impacted_symbols", [])
        affected_files = impact_data.get("impacted_files", [])
        depth = impact_data.get("traversal_depth", 0)

        if not roots:
            return self._result(
                insight="File has no indexed symbols",
                evidence={"file": fmeta},
                heuristic={},
                conclusion="No impact data available",
            )

        direct = [s for s in impacted if s.get("file_id") != file_id]
        transitive_count = len(impacted) - len(direct)
        overall_risk = self.retrieval.ranker.overall_risk(
            incoming=len(direct), depth=depth,
        )

        insight = (
            f"Changing '{fmeta.get('path', file_id)}' impacts "
            f"{len(direct)} external caller(s) across "
            f"{len(affected_files)} file(s) (depth={depth}). "
            f"Risk: {overall_risk}."
        )

        heuristic = {}
        if roots:
            root_risks = []
            for r in roots[:3]:
                meta = self.gq.get_symbol_metadata(r.get("symbol_id", ""))
                if meta:
                    h = self.retrieval.heuristic_analysis(
                        meta.get("id", ""),
                        incoming=len(impacted),
                    )
                    root_risks.append({
                        "symbol": meta.get("name"),
                        "risk": h.get("overall_risk", "LOW"),
                    })
            heuristic = {"root_symbol_risks": root_risks, "overall_risk": overall_risk}

        return self._result(
            insight=insight,
            evidence={
                "file": {"id": file_id, "path": fmeta.get("path")},
                "root_symbols": roots,
                "impact_summary": {
                    "external_callers": len(direct),
                    "transitive_symbols": transitive_count,
                    "affected_files": len(affected_files),
                    "traversal_depth": depth,
                    "overall_risk": overall_risk,
                },
                "affected_files": affected_files,
            },
            heuristic=heuristic,
            conclusion=(
                f"Risk level is {overall_risk}. "
                f"Changing this file affects {len(affected_files)} file(s). "
                "Run full regression suite."
                if overall_risk != "LOW"
                else "Low impact — changes are isolated within the file."
            ),
        )

    # ── builders ────────────────────────────────────────────────────────

    @staticmethod
    def _result(
        insight: str,
        evidence: Dict[str, Any],
        heuristic: Dict[str, Any],
        conclusion: str,
    ) -> Dict[str, Any]:
        return {
            "insight_summary": insight,
            "evidence": evidence,
            "heuristic_analysis": heuristic,
            "conclusion": conclusion,
        }

    @staticmethod
    def _empty(reason: str) -> Dict[str, Any]:
        return {
            "insight_summary": reason,
            "evidence": {},
            "heuristic_analysis": {},
            "conclusion": reason,
        }

    def _build_conclusion(
        self, heuristic: Dict[str, Any], name: str, role: str
    ) -> str:
        risk = heuristic.get("overall_risk", "LOW")
        imp = heuristic.get("importance", 0)
        if risk == "HIGH":
            return (
                f"'{name}' ({role}) has HIGH overall risk. "
                "Review callers and complexity before modifying."
            )
        if imp >= 10:
            return (
                f"'{name}' ({role}) is a high-importance symbol "
                f"(score={imp}). Consider during architecture review."
            )
        return f"'{name}' ({role}) — routine symbol, importance={imp}."

    @staticmethod
    def _hotspot_risk(
        hotspots: List[Dict[str, Any]],
    ) -> tuple[float, str]:
        if not hotspots:
            return 0.0, "LOW"
        avg = sum(h["importance_score"] for h in hotspots) / len(hotspots)
        if avg >= 15:
            return avg, "HIGH"
        if avg >= 8:
            return avg, "MEDIUM"
        return avg, "LOW"
