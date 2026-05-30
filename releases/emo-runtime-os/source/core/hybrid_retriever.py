"""Hybrid Retriever – Phase 10 Semantic + Graph Fusion.

Combines graph-structure importance with semantic similarity to produce
a unified ranking.  Graph-first for structural queries, semantic-first
for discovery, hybrid for general-purpose.

Architecture:
    EmbeddingEngine → SemanticStore ─┐
                                     ├→ HybridRetriever → Orchestrator
    GraphQuery → GraphRetrievalEngine ┘

Dynamic Weighting:
    final_score = w_graph * normalized_graph_importance
                + w_sem  * normalized_semantic_similarity
                + heuristic_bonus

    Weights adapt based on repository size and file context:
      - small repos (<500 files):   w_graph=0.3, w_sem=0.7
      - large repos (>5000 files):  w_graph=0.7, w_sem=0.3
      - test files:                 w_graph=0.2, w_sem=0.8
      - default:                    w_graph=0.6, w_sem=0.4

Heuristic bonuses (applied on top of weighted sum):
    +0.10  if overall_risk == HIGH
    +0.05  if recursion detected
    +0.03  if file depth <= 2 (shallow, core logic)
    -0.03  if file depth > 5 (deep implementation detail)
    -0.05  if unresolved edges > 0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .graph_retrieval import GraphRetrievalEngine
from .semantic_store import SemanticStore
from .embedding_engine import EmbeddingEngine
from .adaptive_weights import (
    AdaptiveWeightEngine,
    profile_from_weights,
    STRATEGY_BALANCED,
)
from .metrics_store import MetricsStore, EVENT_QUERY_EXECUTED, EVENT_RETRIEVAL_COMPLETED
from .query_replay import QueryReplay

logger = logging.getLogger("emo_ai.hybrid_retriever")


# ======================================================================
# RepoStats – lightweight metadata about the indexed repository
# ======================================================================

@dataclass
class RepoStats:
    """Aggregate statistics about the indexed repository."""
    size: int = 0
    total_symbols: int = 0
    languages: List[str] = field(default_factory=list)


# ======================================================================
# WeightsAdvisor – dynamic graph/semantic weighting
# ======================================================================

class WeightsAdvisor:
    """Determines graph vs semantic weights based on repo stats + file path.

    Usage:
        advisor = WeightsAdvisor(RepoStats(size=1200, ...))
        w_g, w_s = advisor.get_weights("auth/service.py")
    """

    # Thresholds
    SMALL_REPO_MAX = 500
    LARGE_REPO_MIN = 5000

    # Weight profiles
    PROFILE_SMALL = (0.3, 0.7)
    PROFILE_LARGE = (0.7, 0.3)
    PROFILE_TEST = (0.2, 0.8)
    PROFILE_DEFAULT = (0.6, 0.4)

    def __init__(self, repo_stats: Optional[RepoStats] = None):
        self.stats = repo_stats or RepoStats()

    def get_weights(self, path: str = "") -> Tuple[float, float]:
        """Return (graph_weight, semantic_weight) for the given file path."""
        # Test/spec files → semantic-heavy
        path_lower = path.lower()
        if any(marker in path_lower for marker in ("test", "spec", "mock", "fixture")):
            return self.PROFILE_TEST

        # Size-based profiles
        if self.stats.size < self.SMALL_REPO_MAX:
            return self.PROFILE_SMALL
        if self.stats.size > self.LARGE_REPO_MIN:
            return self.PROFILE_LARGE

        return self.PROFILE_DEFAULT


# ======================================================================
# HybridRetriever
# ======================================================================

class HybridRetriever:
    """Fuses graph-structure importance with semantic similarity.

    Usage:
        hr = HybridRetriever(graph_engine, semantic_store, embedding_engine)
        result = hr.retrieve("authentication logic")
    """

    # Default fallback weights (when WeightsAdvisor is not provided)
    FALLBACK_GRAPH_WEIGHT = 0.6
    FALLBACK_SEMANTIC_WEIGHT = 0.4
    GRAPH_NORM_CAP = 10.0

    # Heuristic bonuses
    BONUS_HIGH_RISK = 0.10
    BONUS_RECURSIVE = 0.05
    BONUS_SHALLOW_FILE = 0.03
    PENALTY_DEEP_FILE = -0.03
    PENALTY_UNRESOLVED = -0.05

    # Embedding cache
    _EMBED_CACHE: Dict[str, List[float]] = {}

    def __init__(
        self,
        graph_engine: GraphRetrievalEngine,
        semantic_store: Optional[SemanticStore] = None,
        embedding_engine: Optional[EmbeddingEngine] = None,
        weights_advisor: Optional[WeightsAdvisor] = None,
        query_replay: Optional[QueryReplay] = None,
        adaptive_engine: Optional[AdaptiveWeightEngine] = None,
        metrics_store: Optional[MetricsStore] = None,
    ):
        self.graph = graph_engine
        self.store = semantic_store
        self.ee = embedding_engine
        self.weights = weights_advisor
        self.replay = query_replay
        self.adaptive = adaptive_engine
        self.metrics = metrics_store

    @staticmethod
    def _cached_embed(ee: EmbeddingEngine, text: str) -> Optional[List[float]]:
        """Cache embeddings by text hash to avoid recomputation."""
        key = str(hash(text))
        if key in HybridRetriever._EMBED_CACHE:
            return HybridRetriever._EMBED_CACHE[key]
        vec = ee.embed_text(text)
        if vec is None:
            return None
        HybridRetriever._EMBED_CACHE[key] = vec
        if len(HybridRetriever._EMBED_CACHE) > 5000:
            HybridRetriever._EMBED_CACHE.clear()
        return vec

    # ── public entry-point ──────────────────────────────────────────────

    @property
    def semantic_available(self) -> bool:
        return (
            self.store is not None
            and self.store.available
            and self.ee is not None
            and self.ee.available
        )

    def retrieve(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """Top-level retrieval: runs both graph and semantic, merges, ranks.

        Returns a dict with keys:
            query, graph_results, semantic_results, merged_results,
            ranking_scores, improvement_notes, validation_results.
        """
        graph_results = self._retrieve_graph(query, top_k)
        semantic_results = self._retrieve_semantic(query, top_k)
        merged = self.merge(graph_results, semantic_results, top_k)
        ranked = self.rank(merged)
        ranked = self.normalize_scores(ranked)

        improvement_notes = self._build_improvement_notes(
            graph_results, semantic_results, ranked,
        )

        # Collect actual weights used per symbol for transparency
        weights_used: Dict[str, Tuple[float, float]] = {}
        for r in ranked:
            fp = r.get("file_path", "")
            if self.weights:
                w_g, w_s = self.weights.get_weights(fp)
            else:
                w_g, w_s = self.FALLBACK_GRAPH_WEIGHT, self.FALLBACK_SEMANTIC_WEIGHT
            weights_used[r["symbol_id"]] = (w_g, w_s)

        # Determine dominant strategy for logging
        if ranked:
            fp_sample = ranked[0].get("file_path", "")
            w_g_sample, w_s_sample = weights_used.get(ranked[0]["symbol_id"],
                                                       (0.6, 0.4))
            strategy = profile_from_weights(w_g_sample, w_s_sample)
        else:
            strategy = STRATEGY_BALANCED

        # Log to QueryReplay
        replay_id = None
        if self.replay:
            replay_id = self.replay.log(
                query=query,
                results=ranked[:top_k],
                weights_used={k: {"w_graph": round(v[0], 2), "w_sem": round(v[1], 2)}
                              for k, v in weights_used.items()},
                strategy=strategy,
            )

        # Record telemetry events
        if self.metrics:
            self.metrics.record_event(
                EVENT_QUERY_EXECUTED,
                query_id=replay_id,
                strategy=strategy,
                metadata={"query": query[:200], "top_k": top_k,
                          "results_count": len(ranked)},
            )
            self.metrics.record_event(
                EVENT_RETRIEVAL_COMPLETED,
                query_id=replay_id,
                strategy=strategy,
                metadata={"graph_count": len(graph_results),
                          "semantic_count": len(semantic_results),
                          "merged_count": len(ranked)},
            )

        return {
            "query": query,
            "graph_results": graph_results,
            "semantic_results": semantic_results,
            "merged_results": ranked,
            "ranking_scores": [
                {
                    "symbol_id": r["symbol_id"],
                    "symbol_name": r.get("symbol_name", ""),
                    "file_path": r.get("file_path", ""),
                    "graph_importance": r.get("graph_importance", 0),
                    "semantic_score": r.get("semantic_score", 0),
                    "hybrid_score": r["hybrid_score"],
                    "heuristic_bonus": r.get("heuristic_bonus", 0),
                    "final_score": r["final_score"],
                    "w_graph": round(weights_used[r["symbol_id"]][0], 2),
                    "w_sem": round(weights_used[r["symbol_id"]][1], 2),
                }
                for r in ranked
            ],
            "weights_profile": (
                "dynamic" if self.weights else "static"
            ),
            "strategy": strategy,
            "query_id": replay_id,
            "improvement_notes": improvement_notes,
            "validation_results": {
                "auth_test": "PENDING",
                "db_test": "PENDING",
                "payment_test": "PENDING",
            },
        }

    # ── merge ───────────────────────────────────────────────────────────

    def merge(
        self,
        graph_results: List[Dict[str, Any]],
        semantic_results: List[Dict[str, Any]],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Merge graph and semantic results by symbol_id.

        - Symbols in both sources get combined data.
        - Symbols in only one source are still included.
        - Strict deduplication: no duplicate symbol_id.
        """
        seen: Dict[str, Dict[str, Any]] = {}

        for g in graph_results:
            sid = g["symbol_id"]
            fp = g.get("file_path", "")
            seen[sid] = {
                "symbol_id": sid,
                "symbol_name": g.get("symbol_name", ""),
                "file_path": fp,
                "role": g.get("role", "unknown"),
                "graph_importance": g.get("graph_importance", g.get("importance_score", 0)),
                "semantic_score": 0.0,
                "call_count": g.get("call_count", g.get("incoming_calls", 0)),
                "overall_risk": g.get("overall_risk", "LOW"),
                "recursive": g.get("recursive", False),
                "unresolved_edges": g.get("unresolved_edges", 0),
                "file_depth": len(fp.split("/")) if fp else 0,
            }

        for s in semantic_results:
            sid = s["symbol_id"]
            meta = s.get("metadata", {})
            sem_score = s.get("score", 0.0)

            if sid in seen:
                seen[sid].update({
                    "semantic_score": sem_score,
                    "symbol_name": seen[sid]["symbol_name"] or meta.get("name", ""),
                })
            else:
                fp = meta.get("file_path", "")
                seen[sid] = {
                    "symbol_id": sid,
                    "symbol_name": meta.get("name", sid),
                    "file_path": fp,
                    "role": meta.get("role", "unknown"),
                    "graph_importance": 0.0,
                    "semantic_score": sem_score,
                    "call_count": 0,
                    "overall_risk": "LOW",
                    "recursive": False,
                    "unresolved_edges": 0,
                    "file_depth": len(fp.split("/")) if fp else 0,
                }

        merged = list(seen.values())
        logger.debug("Merged %d graph + %d semantic = %d unique symbols",
                      len(graph_results), len(semantic_results), len(merged))
        return merged

    # ── rank ────────────────────────────────────────────────────────────

    def rank(self, merged: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compute hybrid score for every merged entry and sort descending.

        Each entry gets:
            hybrid_score    – weighted sum (before normalisation)
            heuristic_bonus – the bonus/penalty applied
            w_graph, w_sem  – the weights used for this symbol
            final_score     – hybrid_score + heuristic_bonus (clamped [0,1])
        """
        for entry in merged:
            graph_val = entry.get("graph_importance", 0.0)
            sem_val = entry.get("semantic_score", 0.0)

            # Dynamic weights per file path
            fp = entry.get("file_path", "")
            if self.weights:
                w_g, w_s = self.weights.get_weights(fp)
            else:
                w_g, w_s = (self.FALLBACK_GRAPH_WEIGHT, self.FALLBACK_SEMANTIC_WEIGHT)

            # Adaptive boost from learned feedback
            if self.adaptive:
                strat = profile_from_weights(w_g, w_s)
                w_g, w_s = self.adaptive.adjusted_weights(w_g, w_s, strat)

            graph_norm = min(graph_val / self.GRAPH_NORM_CAP, 1.0)
            sem_norm = max(0.0, (sem_val + 1.0) / 2.0)

            hybrid = w_g * graph_norm + w_s * sem_norm
            bonus = self._compute_bonus(entry)
            final_score = max(0.0, min(1.0, hybrid + bonus))

            entry["hybrid_score"] = round(hybrid, 4)
            entry["heuristic_bonus"] = round(bonus, 4)
            entry["w_graph"] = round(w_g, 2)
            entry["w_sem"] = round(w_s, 2)
            entry["final_score"] = round(final_score, 4)

        merged.sort(key=lambda x: (x["final_score"], x.get("graph_importance", 0)),
                    reverse=True)
        return merged

    # ── normalise_scores ────────────────────────────────────────────────

    def normalize_scores(
        self, ranked: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        for entry in ranked:
            entry["final_score"] = max(0.0, min(1.0, entry.get("final_score", 0)))
        return ranked

    # ── internal retrieval helpers ──────────────────────────────────────

    def _retrieve_graph(
        self, query: str, top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        try:
            hotspots = self.graph.ranked_hotspots(limit=top_k)
            enriched = []
            for h in hotspots:
                fp = h.get("file_path", "")
                enriched.append({
                    "symbol_id": h["symbol_id"],
                    "symbol_name": h.get("symbol_name", ""),
                    "file_path": fp,
                    "importance_score": h.get("importance_score", 0),
                    "graph_importance": h.get("importance_score", 0),
                    "role": h.get("role", "unknown"),
                    "call_count": h.get("incoming_calls", 0),
                    "overall_risk": h.get("overall_risk", "LOW"),
                    "recursive": h.get("recursive", False),
                    "unresolved_edges": h.get("unresolved_edges", 0),
                })
            return enriched
        except Exception as e:
            logger.warning("Graph retrieval failed: %s", e)
            return []

    def _retrieve_semantic(
        self, query: str, top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        if not self.semantic_available:
            return []
        qvec = self._cached_embed(self.ee, query)
        if not qvec:
            return []
        raw = self.store.search_similar(qvec, top_k=top_k)
        return [
            {"symbol_id": r["symbol_id"], "score": r["score"],
             "metadata": r.get("metadata", {})}
            for r in raw
        ]

    # ── heuristic bonus logic ───────────────────────────────────────────

    def _compute_bonus(self, entry: Dict[str, Any]) -> float:
        """Compute heuristic bonus/penalty with context signals.

        Signals used:
          overall_risk == HIGH                +0.10
          recursive function                  +0.05
          shallow file (depth ≤ 2)            +0.03
          deep file (depth > 5)               -0.03
          unresolved edges > 0                -0.05
        """
        bonus = 0.0
        if entry.get("overall_risk") == "HIGH":
            bonus += self.BONUS_HIGH_RISK
        if entry.get("recursive"):
            bonus += self.BONUS_RECURSIVE
        fd = entry.get("file_depth", 0)
        if 1 <= fd <= 2:
            bonus += self.BONUS_SHALLOW_FILE
        elif fd > 5:
            bonus += self.PENALTY_DEEP_FILE
        if entry.get("unresolved_edges", 0) > 0:
            bonus += self.PENALTY_UNRESOLVED
        return bonus

    # ── improvement analysis ────────────────────────────────────────────

    def _build_improvement_notes(
        self,
        graph_results: List[Dict[str, Any]],
        semantic_results: List[Dict[str, Any]],
        ranked: List[Dict[str, Any]],
    ) -> str:
        parts: List[str] = []
        g_count = len(graph_results)
        s_count = len(semantic_results)
        m_count = len(ranked)

        parts.append(f"Graph-only returned {g_count} results.")
        parts.append(f"Semantic-only returned {s_count} results.")
        parts.append(f"Merged (deduplicated) returned {m_count} results.")

        g_only = sum(1 for r in ranked if r.get("semantic_score", 1) == 0
                     and r.get("graph_importance", 0) > 0)
        s_only = sum(1 for r in ranked if r.get("graph_importance", 1) == 0
                     and r.get("semantic_score", 0) > 0)
        both = sum(1 for r in ranked if r.get("graph_importance", 0) > 0
                   and r.get("semantic_score", 0) > 0)

        if s_only > 0:
            parts.append(
                f"Semantic layer added {s_only} symbol(s) not in graph — "
                "improved recall."
            )
        if g_only > 0:
            parts.append(
                f"Graph layer contributed {g_only} symbol(s) not found "
                "semantically — preserved structural precision."
            )
        if both > 0:
            parts.append(
                f"{both} symbol(s) found in both layers — cross-confirmed."
            )

        top = ranked[:5] if len(ranked) >= 5 else ranked
        graph_contrib = sum(r.get("graph_importance", 0) for r in top)
        sem_contrib = sum(abs(r.get("semantic_score", 0)) for r in top)
        if graph_contrib >= sem_contrib:
            parts.append("Ranking dominated by structural importance (graph).")
        else:
            parts.append("Ranking influenced by semantic similarity (embedding).")

        # Report weighting profile
        if self.weights:
            profile = (
                f"Dynamic weighting: w_graph/w_sem adapted by repo size "
                f"({self.weights.stats.size} files) and file context."
            )
        else:
            profile = (
                f"Static weighting: w_graph={self.FALLBACK_GRAPH_WEIGHT}, "
                f"w_sem={self.FALLBACK_SEMANTIC_WEIGHT}"
            )
        parts.append(profile)

        return " ".join(parts)

    # ── semantic-search helpers ─────────────────────────────────────────

    def semantic_search(
        self, query_text: str, top_k: int = 10,
    ) -> Dict[str, Any]:
        if not self.semantic_available:
            return {"query": query_text, "total_found": 0, "results": [],
                    "error": "Semantic layer not available"}
        qvec = self._cached_embed(self.ee, query_text)
        if not qvec:
            return {"query": query_text, "total_found": 0, "results": [],
                    "error": "Empty query embedding"}
        raw = self.store.search_similar(qvec, top_k=top_k)
        return {
            "query": query_text,
            "total_found": len(raw),
            "results": [
                {"symbol_id": r["symbol_id"], "score": r["score"],
                 "name": r.get("metadata", {}).get("name", "")}
                for r in raw
            ],
        }

    def find_related_symbols(
        self, symbol_id: str, top_k: int = 5,
    ) -> Dict[str, Any]:
        if not self.semantic_available:
            return {"symbol_id": symbol_id, "total_found": 0, "results": [],
                    "error": "Semantic layer not available"}
        try:
            core = self.graph.retrieve_symbol_core(symbol_id)
        except LookupError:
            return {"symbol_id": symbol_id, "total_found": 0, "results": [],
                    "error": f"Symbol '{symbol_id}' not found in graph"}
        meta = core["meta"]
        text = self.ee.embed_symbol({
            "name": meta.get("name", ""),
            "docstring": meta.get("docstring", ""),
            "symbol_type": meta.get("symbol_type", "function"),
        })
        if not text:
            return {"symbol_id": symbol_id, "total_found": 0, "results": []}
        raw = self.store.search_similar(text, top_k=top_k + 1)
        results = [r for r in raw if r["symbol_id"] != symbol_id][:top_k]
        return {
            "symbol_id": symbol_id,
            "total_found": len(results),
            "results": [
                {"symbol_id": r["symbol_id"], "score": r["score"],
                 "name": r.get("metadata", {}).get("name", "")}
                for r in results
            ],
        }

    def hybrid_search(
        self, query_text: str, top_k: int = 10,
    ) -> Dict[str, Any]:
        """Backward-compatible alias for retrieve()."""
        return self.retrieve(query_text, top_k)

    # ── fallback ────────────────────────────────────────────────────────

    def _fallback_graph(
        self, reason: str, query_text: str, top_k: int,
    ) -> Dict[str, Any]:
        logger.warning("Hybrid search fallback to graph-only: %s", reason)
        try:
            hotspots = self.graph.ranked_hotspots(limit=top_k)
            return {
                "query": query_text,
                "total_found": len(hotspots),
                "graph_results": hotspots,
                "semantic_results": [],
                "merged_results": [
                    {
                        "symbol_id": h["symbol_id"],
                        "symbol_name": h.get("symbol_name", ""),
                        "file_path": h.get("file_path", ""),
                        "graph_importance": h.get("importance_score", 0),
                        "semantic_score": 0.0,
                        "hybrid_score": h.get("importance_score", 0),
                        "heuristic_bonus": 0.0,
                        "final_score": min(h.get("importance_score", 0) / self.GRAPH_NORM_CAP, 1.0),
                        "role": h.get("role", "unknown"),
                        "overall_risk": "LOW",
                        "call_count": h.get("incoming_calls", 0),
                    }
                    for h in hotspots
                ],
                "ranking_scores": [],
                "weights_profile": "static-fallback",
                "improvement_notes": f"Semantic layer unavailable. {reason}",
                "validation_results": {
                    "auth_test": "PENDING",
                    "db_test": "PENDING",
                    "payment_test": "PENDING",
                },
            }
        except Exception as e:
            return {
                "query": query_text,
                "total_found": 0,
                "graph_results": [],
                "semantic_results": [],
                "merged_results": [],
                "ranking_scores": [],
                "error": f"Fallback failed: {e}",
                "improvement_notes": "",
                "validation_results": {},
            }
