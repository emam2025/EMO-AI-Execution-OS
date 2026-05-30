"""AI Context Assembly Engine.

Transforms raw repository graph data into structured LLM-ready context.

Architecture:
    Parser -> Indexer -> DBWriter -> GraphQuery -> AIContextEngine

This layer is read-only.  It consumes GraphQuery results and produces
AI-native context blocks.  No database access, no graph mutations.
"""

from collections import deque
from typing import Any, Dict, List, Optional

from .graph_query import GraphQuery


class AIContextEngine:
    """Read-only context assembly layer over GraphQuery."""

    def __init__(self, graph_query: GraphQuery):
        self.gq = graph_query

    # ── symbol context ──────────────────────────────────────────────────

    def build_symbol_context(
        self,
        symbol_id: str,
        include_unresolved: bool = False,
    ) -> Dict[str, Any]:
        """Generate a full contextual view of a symbol.

        Args:
            symbol_id: Symbol id as text.
            include_unresolved: If True, include unresolved callers/callees.

        Returns:
            Dict with keys: symbol, callers, callees, neighbors,
            summary_stats.
        """
        meta = self.gq.get_symbol_metadata(symbol_id)
        if not meta:
            return {"symbol": None, "callers": [], "callees": [],
                    "neighbors": {"depth_1": [], "depth_2": []},
                    "summary_stats": {}}

        # Callers + callees
        callers = self.gq.get_callers(symbol_id)
        callees = self.gq.get_callees(symbol_id)

        # Depth-1 and depth-2 neighbors (from traverse_depth)
        n1 = self.gq.traverse_depth(
            symbol_id, depth=1, include_unresolved=include_unresolved
        )
        n2 = self.gq.traverse_depth(
            symbol_id, depth=2, include_unresolved=include_unresolved
        )

        incoming = sum(c.get("call_count", 1) for c in callers)
        outgoing = len(callees)

        # Importance score: incoming*2 + outgoing*1 + depth_centrality_bonus
        n1_count = len(n1["nodes"]) - 1  # exclude self
        n2_count = len(n2["nodes"]) - 1
        depth_centrality = n1_count + (n2_count * 0.5)
        importance = round(incoming * 2.0 + outgoing * 1.0 + depth_centrality, 2)

        return {
            "symbol": meta,
            "callers": callers,
            "callees": callees,
            "neighbors": {
                "depth_1": n1["nodes"],
                "depth_2": n2["nodes"],
            },
            "summary_stats": {
                "incoming_calls": incoming,
                "outgoing_calls": outgoing,
                "importance_score": importance,
            },
        }

    # ── file context ────────────────────────────────────────────────────

    def build_file_context(self, file_id: str) -> Dict[str, Any]:
        """Generate AI-ready context for a file.

        Args:
            file_id: File id as text.

        Returns:
            Dict with keys: file, symbols, dependencies, impact_summary,
            hotspots.
        """
        file_meta = self.gq.get_file_metadata(file_id)
        if not file_meta:
            return {"file": None, "symbols": [], "dependencies": [],
                    "impact_summary": [], "hotspots": []}

        symbols = self.gq.get_file_symbols(file_id)
        dependencies = self.gq.get_file_dependencies(file_id)

        # Impact analysis preview
        impact = self.gq.impact_analysis(file_id)

        # Hotspot ranking: sort symbols by importance score
        hotspots = []
        for sym in symbols:
            ctx = self.build_symbol_context(sym["id"])
            hotspots.append({
                "symbol_id": sym["id"],
                "symbol_name": sym["name"],
                "importance_score": ctx["summary_stats"].get("importance_score", 0),
                "symbol_type": sym.get("symbol_type"),
                "incoming_calls": ctx["summary_stats"].get("incoming_calls", 0),
            })
        hotspots.sort(key=lambda h: h["importance_score"], reverse=True)

        return {
            "file": file_meta,
            "symbols": symbols,
            "dependencies": dependencies,
            "impact_summary": impact,
            "hotspots": hotspots[:10],
        }

    # ── context expansion ───────────────────────────────────────────────

    def expand_context(
        self,
        seed_symbol_id: str,
        depth: int = 2,
        min_call_count: int = 0,
    ) -> Dict[str, Any]:
        """Build recursive context expansion for LLMs.

        BFS-based expansion using GraphQuery's traverse_depth, then
        enriches each node with callers/callees metadata.  Deduplicates
        and prioritises high call_count edges.

        Args:
            seed_symbol_id: Starting symbol.
            depth: Max expansion depth.
            min_call_count: Minimum call_count to include a node.

        Returns:
            Dict with keys: root, nodes, edges, stats.
        """
        visited: set[str] = set()
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        queue: deque = deque()
        queue.append((seed_symbol_id, 0))
        visited.add(seed_symbol_id)

        # seed node
        meta = self.gq.get_symbol_metadata(seed_symbol_id)
        if meta:
            nodes.append({
                "symbol_id": seed_symbol_id,
                "symbol_name": meta.get("name"),
                "depth": 0,
                "importance": 0,
                "callers_count": 0,
                "callees_count": 0,
            })
        else:
            nodes.append({
                "symbol_id": seed_symbol_id,
                "depth": 0,
            })

        while queue:
            current_id, current_depth = queue.popleft()
            next_depth = current_depth + 1
            if next_depth > depth:
                continue

            # Callees of current node
            callees = self.gq.get_callees(current_id)
            for callee in callees:
                cid = callee["symbol_id"]
                cc = callee.get("properties", {}).get("call_count", 1)
                if cc < min_call_count:
                    continue
                edges.append({
                    "source_id": current_id,
                    "target_id": cid,
                    "edge_type": callee["edge_type"],
                    "call_count": cc,
                })

                if cid not in visited:
                    visited.add(cid)
                    m = self.gq.get_symbol_metadata(cid)
                    callers_of_c = self.gq.get_callers(cid)
                    callees_of_c = self.gq.get_callees(cid)
                    importance = (
                        sum(c.get("call_count", 1) for c in callers_of_c) * 2
                        + len(callees_of_c)
                    )
                    nodes.append({
                        "symbol_id": cid,
                        "symbol_name": m.get("name") if m else None,
                        "depth": next_depth,
                        "importance": importance,
                        "callers_count": len(callers_of_c),
                        "callees_count": len(callees_of_c),
                    })
                    queue.append((cid, next_depth))

            # Callers of current node (reverse direction)
            callers = self.gq.get_callers(current_id)
            for caller in callers:
                cid = caller["symbol_id"]
                cc = caller.get("call_count", 1)
                if cc < min_call_count:
                    continue
                edges.append({
                    "source_id": cid,
                    "target_id": current_id,
                    "edge_type": caller["edge_type"],
                    "call_count": cc,
                })

                if cid not in visited:
                    visited.add(cid)
                    m = self.gq.get_symbol_metadata(cid)
                    callers_of_c = self.gq.get_callers(cid)
                    callees_of_c = self.gq.get_callees(cid)
                    importance = (
                        sum(c.get("call_count", 1) for c in callers_of_c) * 2
                        + len(callees_of_c)
                    )
                    nodes.append({
                        "symbol_id": cid,
                        "symbol_name": m.get("name") if m else None,
                        "depth": next_depth,
                        "importance": importance,
                        "callers_count": len(callers_of_c),
                        "callees_count": len(callees_of_c),
                    })
                    queue.append((cid, next_depth))

        # Sort edges by call_count descending for LLM priority
        edges.sort(key=lambda e: e.get("call_count", 0), reverse=True)

        return {
            "root": seed_symbol_id,
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "depth_achieved": min(depth, max(n["depth"] for n in nodes)),
            },
        }

    # ── LLM-ready context ───────────────────────────────────────────────

    def build_llm_context(self, symbol_id: str) -> Dict[str, Any]:
        """Convert graph data into LLM prompt-ready format.

        This is the primary entry point for AI agents.  Produces three
        representations: structured JSON, a human-readable text block,
        and key risk/dependency analysis.

        Args:
            symbol_id: Symbol id as text.

        Returns:
            Dict with keys: system_context, structured_context,
            llm_ready_prompt_block.
        """
        # 1. Symbol context
        sym_ctx = self.build_symbol_context(symbol_id)

        # 2. Expansion (depth 2, both directions)
        expansion = self.expand_context(symbol_id, depth=2)

        # 3. Impact preview (if we know the file)
        meta = sym_ctx.get("symbol")
        file_ctx = {}
        if meta and meta.get("file_id"):
            file_ctx = self.build_file_context(meta["file_id"])

        # ── system_context ──────────────────────────────────────────
        system_context = (
            "You are an AI code intelligence assistant analysing a "
            "repository graph.  The data below describes symbol "
            f"'{meta.get('name', symbol_id) if meta else symbol_id}' "
            "and its surrounding call graph.  Use this context to answer "
            "questions about code structure, dependencies, and impact."
        )

        # ── structured_context ──────────────────────────────────────
        stats = sym_ctx.get("summary_stats", {})
        hotspots = file_ctx.get("hotspots", [])

        key_deps = []
        for callee in sym_ctx.get("callees", []):
            key_deps.append({
                "type": "callee",
                "symbol": callee.get("symbol_name"),
                "edge_type": callee.get("edge_type"),
            })
        for caller in sym_ctx.get("callers", []):
            key_deps.append({
                "type": "caller",
                "symbol": caller.get("symbol_name"),
                "call_count": caller.get("call_count"),
            })

        risk_analysis = []
        for n in expansion.get("nodes", []):
            if n.get("depth", 0) >= 2:
                risk_analysis.append({
                    "symbol_id": n["symbol_id"],
                    "symbol_name": n.get("symbol_name"),
                    "depth": n["depth"],
                    "importance": n.get("importance", 0),
                })
        risk_analysis.sort(key=lambda r: r.get("importance", 0), reverse=True)

        structured_context = {
            "symbol_context": sym_ctx,
            "graph_summary": expansion.get("stats", {}),
            "key_dependencies": key_deps,
            "risk_analysis": risk_analysis[:5],
            "hotspots": hotspots,
        }

        # ── llm_ready_prompt_block ──────────────────────────────────
        lines: List[str] = []
        lines.append(f"=== Symbol: {meta.get('name', symbol_id) if meta else symbol_id} ===")

        if meta:
            lines.append(f"Type: {meta.get('symbol_type', 'unknown')}")
            if meta.get("signature"):
                lines.append(f"Signature: {meta['signature']}")

        lines.append("")
        lines.append("--- Callers ---")
        for c in sym_ctx.get("callers", []):
            lines.append(
                f"  {c['symbol_name']} ({c['call_count']} calls)"
            )
        if not sym_ctx.get("callers"):
            lines.append("  (none)")

        lines.append("")
        lines.append("--- Callees ---")
        for c in sym_ctx.get("callees", []):
            lines.append(
                f"  {c['symbol_name']} ({c['edge_type']})"
            )
        if not sym_ctx.get("callees"):
            lines.append("  (none)")

        lines.append("")
        lines.append("--- Call Graph Statistics ---")
        lines.append(f"  Incoming calls: {stats.get('incoming_calls', 0)}")
        lines.append(f"  Outgoing calls: {stats.get('outgoing_calls', 0)}")
        lines.append(f"  Importance score: {stats.get('importance_score', 0)}")
        lines.append(f"  Reachable nodes (depth 2): {expansion['stats']['node_count']}")

        if key_deps:
            lines.append("")
            lines.append("--- Key Dependencies ---")
            for dep in key_deps[:5]:
                lines.append(f"  [{dep['type']}] {dep['symbol']}")

        if risk_analysis:
            lines.append("")
            lines.append("--- Risk / High-Impact Dependents ---")
            for r in risk_analysis[:3]:
                lines.append(
                    f"  {r['symbol_name']} (depth={r['depth']}, "
                    f"importance={r['importance']})"
                )

        if hotspots:
            lines.append("")
            lines.append("--- Hotspots in File ---")
            for h in hotspots[:3]:
                lines.append(
                    f"  {h['symbol_name']} (importance={h['importance_score']})"
                )

        llm_block = "\n".join(lines)

        return {
            "system_context": system_context,
            "structured_context": structured_context,
            "llm_ready_prompt_block": llm_block,
        }
