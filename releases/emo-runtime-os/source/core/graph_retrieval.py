"""Graph-first Retrieval + Heuristics Layer – Phase 8.

Retrieval engine built entirely on graph structure, with heuristic
ranking and smart filtering.  No embeddings, no vector DB, no AST.

Architecture:
    … → GraphQuery → AIContextEngine → GraphRetrievalEngine → AI Agent

Every result is backed by graph evidence.  Insufficient data yields
"insufficient graph data".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from .graph_query import GraphQuery
from .ai_context_engine import AIContextEngine


# ======================================================================
# HeuristicRanker – pure scoring, no side effects
# ======================================================================

class HeuristicRanker:
    """Standardised heuristic scoring for symbol importance and risk.

    Formula used:
        importance = incoming*2.0 + outgoing*1.0 + depth_centrality*0.5
                     + call_count_weight - complexity_penalty

    where:
        complexity_penalty = max(0, (cyclomatic - 5) * 0.5)
    """

    IMPORTANCE_FORMULA = (
        "incoming*2.0 + outgoing*1.0 + depth_centrality*0.5 "
        "+ call_count_weight - complexity_penalty"
    )

    # ── importance ──────────────────────────────────────────────────────

    @staticmethod
    def importance(
        incoming_calls: int = 0,
        outgoing_calls: int = 0,
        depth_centrality: float = 0.0,
        call_count_weight: float = 0.0,
        cyclomatic: int = 1,
    ) -> float:
        """Compute the standardised importance score for a symbol."""
        penalty = max(0.0, (cyclomatic - 5) * 0.5)
        return (
            incoming_calls * 2.0
            + outgoing_calls * 1.0
            + depth_centrality * 0.5
            + call_count_weight
            - penalty
        )

    # ── risk heuristics ─────────────────────────────────────────────────

    @staticmethod
    def fan_in_risk(incoming: int) -> str:
        if incoming >= 5:
            return "HIGH"
        if incoming >= 2:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def fan_out_risk(outgoing: int) -> str:
        if outgoing >= 8:
            return "HIGH"
        if outgoing >= 4:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def depth_risk(depth: int) -> str:
        if depth > 3:
            return "HIGH"
        if depth > 2:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def complexity_risk(cyclomatic: int) -> str:
        if cyclomatic > 7:
            return "HIGH"
        if cyclomatic > 4:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def recursion_risk(is_recursive: bool) -> str:
        return "MEDIUM" if is_recursive else "LOW"

    @staticmethod
    def unresolved_risk(unresolved_count: int) -> str:
        if unresolved_count >= 3:
            return "HIGH"
        if unresolved_count >= 1:
            return "MEDIUM"
        return "LOW"

    # ── combined risk ───────────────────────────────────────────────────

    @classmethod
    def overall_risk(cls, **kwargs: Any) -> str:
        """Determine the highest risk across all dimensions."""
        risks = [
            cls.fan_in_risk(kwargs.get("incoming", 0)),
            cls.fan_out_risk(kwargs.get("outgoing", 0)),
            cls.depth_risk(kwargs.get("depth", 0)),
            cls.complexity_risk(kwargs.get("cyclomatic", 1)),
            cls.recursion_risk(kwargs.get("is_recursive", False)),
            cls.unresolved_risk(kwargs.get("unresolved", 0)),
        ]
        if "HIGH" in risks:
            return "HIGH"
        if "MEDIUM" in risks:
            return "MEDIUM"
        return "LOW"

    @classmethod
    def risk_breakdown(cls, **kwargs: Any) -> List[Dict[str, str]]:
        dimensions = [
            ("fan_in", cls.fan_in_risk(kwargs.get("incoming", 0)),
             f"{kwargs.get('incoming', 0)} incoming callers"),
            ("fan_out", cls.fan_out_risk(kwargs.get("outgoing", 0)),
             f"{kwargs.get('outgoing', 0)} outgoing calls"),
            ("depth", cls.depth_risk(kwargs.get("depth", 0)),
             f"traversal depth = {kwargs.get('depth', 0)}"),
            ("complexity", cls.complexity_risk(kwargs.get("cyclomatic", 1)),
             f"cyclomatic complexity = {kwargs.get('cyclomatic', 1)}"),
            ("recursion", cls.recursion_risk(kwargs.get("is_recursive", False)),
             f"recursive = {kwargs.get('is_recursive', False)}"),
            ("unresolved", cls.unresolved_risk(kwargs.get("unresolved", 0)),
             f"{kwargs.get('unresolved', 0)} unresolved edge(s)"),
        ]
        return [
            {"dimension": d, "risk": r, "evidence": e}
            for d, r, e in dimensions
        ]


# ======================================================================
# SmartFilter – deduplication, noise removal, unresolved-edge control
# ======================================================================

class SmartFilter:
    """Configurable filter pipeline for graph result nodes."""

    @staticmethod
    def deduplicate(items: List[Dict[str, Any]], key: str = "symbol_id") -> List[Dict[str, Any]]:
        seen: Set[Any] = set()
        out: List[Dict[str, Any]] = []
        for item in items:
            k = item.get(key)
            if k is not None and k not in seen:
                seen.add(k)
                out.append(item)
        return out

    @staticmethod
    def by_min_importance(
        items: List[Dict[str, Any]], threshold: float = 0.0,
        score_key: str = "importance_score",
    ) -> List[Dict[str, Any]]:
        if not threshold:
            return items
        return [i for i in items if (i.get(score_key) or 0) >= threshold]

    @staticmethod
    def by_max_depth(
        items: List[Dict[str, Any]], max_depth: int = 3,
    ) -> List[Dict[str, Any]]:
        return [i for i in items if (i.get("depth") or 0) <= max_depth]

    @staticmethod
    def exclude_unresolved(
        items: List[Dict[str, Any]], flag_key: str = "resolved",
    ) -> List[Dict[str, Any]]:
        return [i for i in items if i.get(flag_key, 1) != 0]

    @staticmethod
    def limit(items: List[Dict[str, Any]], n: int = 20) -> List[Dict[str, Any]]:
        return items[:n]

    @classmethod
    def pipeline(
        cls,
        items: List[Dict[str, Any]],
        dedup_key: str = "symbol_id",
        min_importance: float = 0.0,
        max_depth: int = 3,
        exclude_unresolved: bool = True,
        max_items: int = 20,
    ) -> List[Dict[str, Any]]:
        result = items
        result = cls.deduplicate(result, key=dedup_key)
        if exclude_unresolved:
            result = cls.exclude_unresolved(result)
        result = cls.by_max_depth(result, max_depth)
        result = cls.by_min_importance(result, min_importance)
        result = cls.limit(result, max_items)
        return result


# ======================================================================
# GraphRetrievalEngine – retrieval + ranking + filtering
# ======================================================================

class GraphRetrievalEngine:
    """Graph-first retrieval engine with heuristic ranking and filtering.

    Wraps GraphQuery and AIContextEngine to provide filtered, ranked
    results using only graph structure.  No SQL, no AST, no embeddings.
    """

    def __init__(self, gq: GraphQuery, ctx: AIContextEngine):
        self.gq = gq
        self.ctx = ctx
        self.ranker = HeuristicRanker()
        self.filter = SmartFilter()

    # ── symbol retrieval ────────────────────────────────────────────────

    def retrieve_symbol_core(
        self, symbol_id: str,
        include_unresolved: bool = False,
    ) -> Dict[str, Any]:
        """Fetch filtered metadata + static analysis for a symbol.

        Returns a dict with keys: meta, static_analysis, or raises
        LookupError if the symbol does not exist.
        """
        meta = self.gq.get_symbol_metadata(symbol_id)
        if not meta:
            raise LookupError(f"Symbol '{symbol_id}' not found")
        sa = meta.get("properties", {})
        return {"meta": meta, "static_analysis": sa}

    # ── callers / callees with filtering ────────────────────────────────

    def retrieve_callers(
        self, symbol_id: str,
        min_calls: int = 1,
        max_items: int = 20,
    ) -> List[Dict[str, Any]]:
        """Filtered callers, sorted by call_count descending."""
        raw = self.gq.get_callers(symbol_id, min_calls=0)
        filtered = [c for c in raw if c.get("call_count", 0) >= min_calls]
        filtered.sort(key=lambda c: c.get("call_count", 0), reverse=True)
        return self.filter.limit(filtered, max_items)

    def retrieve_callees(
        self, symbol_id: str,
        max_items: int = 20,
    ) -> List[Dict[str, Any]]:
        """Filtered callees."""
        raw = self.gq.get_callees(symbol_id)
        return self.filter.limit(raw, max_items)

    # ── ranked hotspots ────────────────────────────────────────────────

    def ranked_hotspots(
        self, limit: int = 10,
        min_importance: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Hotspots ranked by the standardised importance formula.

        Uses batch queries instead of per-symbol round-trips.
        Returns risk data inline so callers need no extra heuristic_analysis.
        """
        tops = self.gq.top_symbols(limit * 2)

        if not tops:
            return []

        # Batch-load all metadata and callee counts (2 queries instead of 2n)
        sids = [t["symbol_id"] for t in tops]
        meta_batch = self.gq.batch_symbol_metadata(sids)
        callee_batch = self.gq.batch_callee_counts(sids)

        enriched: List[Dict[str, Any]] = []
        for t in tops:
            sid = t["symbol_id"]
            meta = meta_batch.get(sid)
            if meta is None:
                continue
            props = meta["properties"]
            sa = props  # static_analysis lives in properties
            cyclomatic = sa.get("complexity", {}).get("cyclomatic", 1)
            is_recursive = sa.get("behavior", {}).get("is_recursive", False)

            incoming = t["total_calls"]
            outgoing = callee_batch.get(sid, 0)
            dc = float(outgoing)

            score = self.ranker.importance(
                incoming_calls=incoming,
                outgoing_calls=outgoing,
                depth_centrality=dc,
                cyclomatic=cyclomatic,
            )

            if score < min_importance:
                continue

            risk = self.ranker.overall_risk(
                incoming=incoming,
                outgoing=outgoing,
                depth=0,
                cyclomatic=cyclomatic,
                is_recursive=is_recursive,
                unresolved=0,
            )

            enriched.append({
                "symbol_id": sid,
                "symbol_name": t["symbol_name"],
                "file_path": t.get("file_path"),
                "incoming_calls": incoming,
                "outgoing_calls": outgoing,
                "cyclomatic": cyclomatic,
                "depth_centrality": round(dc, 1),
                "importance_score": round(score, 2),
                "role": sa.get("role", "unknown"),
                "overall_risk": risk,
                "recursive": is_recursive,
                "unresolved_edges": 0,
            })

        enriched.sort(key=lambda h: h["importance_score"], reverse=True)
        return enriched[:limit]

    # ── impact chain ────────────────────────────────────────────────────

    def retrieve_impact_chain(
        self, symbol_id: str,
        max_depth: int = 3,
        min_call_count: int = 0,
    ) -> Dict[str, Any]:
        """Filtered impact chain for a symbol.

        Returns deduplicated, depth-limited impact data with heuristic
        scoring applied to each affected node.
        """
        meta = self.gq.get_symbol_metadata(symbol_id)
        if not meta:
            raise LookupError(f"Symbol '{symbol_id}' not found")

        # Direct callers (depth 1)
        callers = self.gq.get_callers(symbol_id, min_calls=min_call_count)
        caller_names: Set[str] = set()

        direct: List[Dict[str, Any]] = []
        for c in callers:
            sid = c["symbol_id"]
            if sid in caller_names:
                continue
            caller_names.add(sid)
            cm = self.gq.get_symbol_metadata(sid)
            sa_c = cm.get("properties", {}) if cm else {}
            import_score = self.ranker.importance(
                incoming_calls=c.get("call_count", 1),
                outgoing_calls=len(self.gq.get_callees(sid)),
                cyclomatic=sa_c.get("complexity", {}).get("cyclomatic", 1),
            )
            direct.append({
                "symbol_id": sid,
                "symbol_name": c.get("symbol_name"),
                "call_count": c.get("call_count", 1),
                "depth": 1,
                "importance_score": round(import_score, 2),
            })

        # Transitive (depth 2+) — BFS via get_callers
        transitive: List[Dict[str, Any]] = []
        queue: List[Tuple[str, int]] = []
        visited: Set[str] = set(s["symbol_id"] for s in direct)
        visited.add(symbol_id)  # don't revisit self

        for d in direct:
            queue.append((d["symbol_id"], 1))

        while queue:
            current_id, depth = queue.pop(0)
            next_depth = depth + 1
            if next_depth > max_depth:
                continue
            deeper = self.gq.get_callers(current_id, min_calls=min_call_count)
            for c in deeper:
                cid = c["symbol_id"]
                if cid in visited:
                    continue
                visited.add(cid)
                cm = self.gq.get_symbol_metadata(cid)
                sa_c = cm.get("properties", {}) if cm else {}
                import_score = self.ranker.importance(
                    incoming_calls=c.get("call_count", 1),
                    outgoing_calls=len(self.gq.get_callees(cid)),
                    cyclomatic=sa_c.get("complexity", {}).get("cyclomatic", 1),
                )
                transitive.append({
                    "symbol_id": cid,
                    "symbol_name": c.get("symbol_name"),
                    "call_count": c.get("call_count", 1),
                    "depth": next_depth,
                    "importance_score": round(import_score, 2),
                })
                queue.append((cid, next_depth))

        overall_risk = self.ranker.overall_risk(
            incoming=len(direct),
            depth=max_depth,
            cyclomatic=meta.get("properties", {}).get("complexity", {}).get("cyclomatic", 1),
        )

        return {
            "target": {
                "symbol_id": symbol_id,
                "name": meta.get("name"),
                "file_id": meta.get("file_id"),
            },
            "direct_impact": direct,
            "transitive_impact": transitive,
            "total_impacted": len(direct) + len(transitive),
            "max_depth_reached": min(max_depth, max([d.get("depth", 1) for d in direct + transitive] + [1])),
            "overall_risk": overall_risk,
        }

    # ── heuristic analysis bundle ───────────────────────────────────────

    def heuristic_analysis(
        self,
        symbol_id: str,
        incoming: int = 0,
        outgoing: int = 0,
        depth: int = 0,
    ) -> Dict[str, Any]:
        """Compute the full heuristic analysis bundle for a symbol."""
        try:
            core = self.retrieve_symbol_core(symbol_id)
        except LookupError:
            return {}

        sa = core["static_analysis"]
        behaviour = sa.get("behavior", {})
        complexity = sa.get("complexity", {})

        cyclomatic = complexity.get("cyclomatic", 1)
        is_recursive = behaviour.get("is_recursive", False)

        unresolved_count = 0  # count from graph edges would need extra query
        # quick estimate: number of unresolved edges
        try:
            t1 = self.gq.traverse_depth(symbol_id, depth=1, include_unresolved=True)
            resolved_count = sum(1 for e in t1.get("edges", []) if e.get("resolved", 0))
            total_edges = len(t1.get("edges", []))
            unresolved_count = total_edges - resolved_count
        except Exception:
            pass

        score = self.ranker.importance(
            incoming_calls=incoming,
            outgoing_calls=outgoing,
            cyclomatic=cyclomatic,
        )

        risk_breakdown = self.ranker.risk_breakdown(
            incoming=incoming,
            outgoing=outgoing,
            depth=depth,
            cyclomatic=cyclomatic,
            is_recursive=is_recursive,
            unresolved=unresolved_count,
        )

        overall_risk = self.ranker.overall_risk(
            incoming=incoming,
            outgoing=outgoing,
            depth=depth,
            cyclomatic=cyclomatic,
            is_recursive=is_recursive,
            unresolved=unresolved_count,
        )

        return {
            "importance": round(score, 2),
            "importance_formula": self.ranker.IMPORTANCE_FORMULA,
            "risk_breakdown": risk_breakdown,
            "overall_risk": overall_risk,
        }
