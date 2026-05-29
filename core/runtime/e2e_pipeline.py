"""E2E Pipeline — reusable construction for the full-chain integration pipeline.

Routers import from here instead of core.* directly.  This module is under
core.runtime.* so it passes the router_isolation_check AST gate.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.composition.root import build_minimal_runtime

logger = logging.getLogger("emo_ai.e2e_pipeline")


def build_e2e_components(
    repo_path: str,
    db_path: str,
    ai_index_dir: Path,
    force_reindex: bool = False,
    worker_pool_size: int = 4,
) -> dict:
    """Construct all pipeline components for a given repo.

    Returns dict with keys:
        indexer, index_stats, gq, gre, agent, ctx, hybrid,
        memory, metrics, cache, runtime, replay
    """
    from core.repository_indexer import RepositoryIndexer
    from core.graph_query import GraphQuery
    from core.graph_retrieval import GraphRetrievalEngine
    from core.ai_agent import CodeIntelligenceAgent
    from core.ai_context_engine import AIContextEngine
    from core.hybrid_retriever import (
        HybridRetriever, WeightsAdvisor, RepoStats,
    )
    from core.embedding_engine import EmbeddingEngine
    from core.semantic_store import SemanticStore
    from core.query_replay import QueryReplay
    from core.adaptive_weights import AdaptiveWeightEngine
    from core.feedback_loop import RankingFeedbackLoop
    from core.metrics_store import MetricsStore
    from core.execution_memory import ExecutionMemory
    from core.execution_cache import ExecutionCache
    from core.dag_replay import DAGReplayEngine

    components: dict = {}

    # Phase 1: Index
    indexer = RepositoryIndexer(repo_root=repo_path, db_path=db_path)
    components["index_stats"] = indexer.scan_and_index(force_full=force_reindex)
    components["indexer"] = indexer

    # Phases 2-4: Graph layer
    gq = GraphQuery(db_path)
    gre = GraphRetrievalEngine(gq)
    agent = CodeIntelligenceAgent(gq, gre)
    ctx = AIContextEngine(gq)
    components.update(gq=gq, gre=gre, agent=agent, ctx=ctx)

    # Phase 10: Semantic layer
    hybrid: Optional[HybridRetriever] = None
    try:
        ss_path = str(ai_index_dir / "semantic.index")
        qr_path = str(ai_index_dir / "query_logs.db")
        ee = EmbeddingEngine()
        ss = SemanticStore(ss_path)
        qr = QueryReplay(qr_path)
        loop = RankingFeedbackLoop()
        metrics_inst = MetricsStore(str(ai_index_dir / "metrics.db"))
        awe = AdaptiveWeightEngine(loop, metrics_store=metrics_inst)
        wa = WeightsAdvisor(
            RepoStats(size=100, total_symbols=10, languages=["python"]),
        )
        hybrid = HybridRetriever(
            gre, ss, ee, weights_advisor=wa,
            query_replay=qr, adaptive_engine=awe,
            metrics_store=metrics_inst,
        )
        components["metrics"] = metrics_inst
    except Exception as e:
        logger.warning("Semantic layer unavailable (non-fatal): %s", e)

    components["hybrid"] = hybrid

    # Phases 14-16: Memory, Runtime, Replay
    mem_path = str(ai_index_dir / "execution_memory.db")
    metrics_path = str(ai_index_dir / "metrics.db")
    memory = ExecutionMemory(mem_path)
    metrics = MetricsStore(metrics_path)
    cache = ExecutionCache(
        db_path=str(ai_index_dir / "execution_cache.db"),
        max_entries=2000,
        default_ttl_seconds=3600,
    )

    runtime = build_minimal_runtime(
        gq=gq, gre=gre, agent=agent, ctx=ctx,
        hybrid=hybrid, memory=memory, metrics=metrics,
        cache=cache, worker_pool_size=worker_pool_size,
    )

    replay = DAGReplayEngine(memory)

    components.update(
        memory=memory, metrics=metrics, cache=cache,
        runtime=runtime, replay=replay,
    )

    return components


def run_e2e_pipeline(
    repo_path: str,
    query: str,
    force_reindex: bool = False,
    include_trace: bool = True,
    runtime: Any = None,
    worker_pool_size: int = 4,
) -> dict:
    """Run the full E2E pipeline and return results as a plain dict.

    This is the recommended entry point for routers.
    """
    import time

    start = time.time()
    resolved = str(Path(repo_path).expanduser().resolve())
    repo_dir = Path(resolved)
    ai_index_dir = repo_dir / ".ai" / "index"
    ai_index_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(ai_index_dir / "repository.db")

    components = build_e2e_components(
        repo_path=resolved,
        db_path=db_path,
        ai_index_dir=ai_index_dir,
        force_reindex=force_reindex,
        worker_pool_size=worker_pool_size,
    )

    rt = runtime or components["runtime"]

    try:
        result = rt.execute(query)
    except Exception as e:
        logger.error("Execution failed: %s", e)
        raise

    elapsed = round(time.time() - start, 3)

    trace_result: Optional[Dict[str, Any]] = None
    session_id = result.get("session_id")
    if include_trace and session_id:
        try:
            replay = components["replay"]
            replay_steps = replay.step_through(session_id)
            viz = replay.visualize(session_id)
            trace_result = {
                "session_id": session_id,
                "replay": replay_steps,
                "visualization": viz,
            }
        except Exception as e:
            logger.warning("Trace retrieval failed: %s", e)

    return {
        "repo_path": resolved,
        "query": query,
        "duration_seconds": elapsed,
        "indexing": {
            "files_scanned": components.get("index_stats", {}).get("files_scanned", 0),
            "files_indexed": components.get("index_stats", {}).get("files_indexed", 0),
            "files_skipped": components.get("index_stats", {}).get("files_skipped", 0),
            "files_removed": components.get("index_stats", {}).get("files_removed", 0),
            "errors": components.get("index_stats", {}).get("errors", 0),
            "edges_resolved": components.get("index_stats", {}).get("edges_resolved", 0),
            "duration_seconds": components.get("index_stats", {}).get("duration_seconds", 0),
        },
        "execution": {
            "plan": result.get("plan_summary"),
            "tools_used": result.get("tools_used"),
            "steps": result.get("step_results"),
            "answer": result.get("final_answer"),
        },
        "trace": trace_result,
    }
