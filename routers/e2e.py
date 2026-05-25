"""E2E Pipeline Router — Full-Chain Integration Endpoint.

Runs the complete AI pipeline against a target repository:
  index → graph → semantic → hybrid → DAG execution → replay → telemetry

Endpoint:
  POST /api/e2e/pipeline — Execute the full pipeline
"""

from __future__ import annotations

import logging
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from core.graph_query import GraphQuery
from core.graph_retrieval import GraphRetrievalEngine
from core.ai_agent import CodeIntelligenceAgent
from core.ai_context_engine import AIContextEngine
from core.hybrid_retriever import HybridRetriever
from core.unified_runtime import UnifiedRuntime
from core.metrics_store import MetricsStore
from core.execution_memory import ExecutionMemory
from core.dag_replay import DAGReplayEngine
from core.repository_indexer import RepositoryIndexer
from core.execution_cache import ExecutionCache

logger = logging.getLogger("emo_ai.router")

router = APIRouter(prefix="/api/e2e", tags=["e2e"])


@router.post("/pipeline")
def run_pipeline(
    repo_path: str,
    query: str,
    force_reindex: bool = False,
    include_trace: bool = True,
):
    """Execute the full AI pipeline: index → graph → semantic → DAG → trace.

    Args:
        repo_path: Absolute path to the target repository.
        query: Natural-language query about the codebase.
        force_reindex: If true, re-index all files regardless of changes.
        include_trace: If true, include DAG trace and replay in response.
    """
    start = time.time()
    resolved = str(Path(repo_path).expanduser().resolve())
    repo_dir = Path(resolved)
    if not repo_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Repo path not found: {resolved}")

    ai_index_dir = repo_dir / ".ai" / "index"
    ai_index_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(ai_index_dir / "repository.db")

    # ----------------------------------------------------------------
    # Phase 1: Index the repository
    # ----------------------------------------------------------------
    try:
        indexer = RepositoryIndexer(repo_root=resolved, db_path=db_path)
        index_stats = indexer.scan_and_index(force_full=force_reindex)
        logger.info(
            "Indexed %s: %d files scanned, %d indexed, %d errors",
            resolved, index_stats.get("files_scanned", 0),
            index_stats.get("files_indexed", 0), index_stats.get("errors", 0),
        )
    except Exception as e:
        logger.error("Indexing failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")

    # ----------------------------------------------------------------
    # Phase 2–4: Graph layer, Agent, Semantic
    # ----------------------------------------------------------------
    try:
        gq = GraphQuery(db_path)
        gre = GraphRetrievalEngine(gq)
        agent = CodeIntelligenceAgent(gq, gre)
        ctx = AIContextEngine(gq)
    except Exception as e:
        logger.error("Graph layer init failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Graph init failed: {e}")

    # ----------------------------------------------------------------
    # Phase 10: Semantic layer (optional)
    # ----------------------------------------------------------------
    hybrid: Optional[HybridRetriever] = None
    try:
        from core.embedding_engine import EmbeddingEngine
        from core.semantic_store import SemanticStore
        from core.hybrid_retriever import WeightsAdvisor, RepoStats
        from core.query_replay import QueryReplay
        from core.adaptive_weights import AdaptiveWeightEngine
        from core.feedback_loop import RankingFeedbackLoop

        ss_path = str(ai_index_dir / "semantic.index")
        qr_path = str(ai_index_dir / "query_logs.db")
        ee = EmbeddingEngine()
        ss = SemanticStore(ss_path)
        qr = QueryReplay(qr_path)
        loop = RankingFeedbackLoop()
        metrics = MetricsStore(str(ai_index_dir / "metrics.db"))
        awe = AdaptiveWeightEngine(loop, metrics_store=metrics)
        wa = WeightsAdvisor(RepoStats(size=100, total_symbols=10, languages=["python"]))
        hybrid = HybridRetriever(gre, ss, ee, weights_advisor=wa,
                                  query_replay=qr, adaptive_engine=awe,
                                  metrics_store=metrics)
    except Exception as e:
        logger.warning("Semantic layer unavailable (non-fatal): %s", e)

    # ----------------------------------------------------------------
    # Phase 14–16: Memory, Runtime, Replay
    # ----------------------------------------------------------------
    mem_path = str(ai_index_dir / "execution_memory.db")
    metrics_path = str(ai_index_dir / "metrics.db")
    memory = ExecutionMemory(mem_path)
    metrics = MetricsStore(metrics_path)
    cache = ExecutionCache(
        db_path=str(ai_index_dir / "execution_cache.db"),
        max_entries=2000, default_ttl_seconds=3600,
    )

    runtime = UnifiedRuntime(
        gq, gre, agent, ctx,
        hybrid=hybrid, memory=memory, metrics=metrics,
        cache=cache, worker_pool_size=4,
    )

    replay = DAGReplayEngine(memory)

    # ----------------------------------------------------------------
    # Execute
    # ----------------------------------------------------------------
    try:
        result = runtime.execute(query)
    except Exception as e:
        logger.error("Execution failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Execution failed: {e}")

    elapsed = round(time.time() - start, 3)

    # ----------------------------------------------------------------
    # Optional: DAG trace
    # ----------------------------------------------------------------
    trace_result: Optional[Dict[str, Any]] = None
    session_id = result.get("session_id")
    if include_trace and session_id:
        try:
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
            "files_scanned": index_stats.get("files_scanned", 0),
            "files_indexed": index_stats.get("files_indexed", 0),
            "files_skipped": index_stats.get("files_skipped", 0),
            "files_removed": index_stats.get("files_removed", 0),
            "errors": index_stats.get("errors", 0),
            "edges_resolved": index_stats.get("edges_resolved", 0),
            "duration_seconds": index_stats.get("duration_seconds", 0),
        },
        "execution": {
            "plan": result.get("plan_summary"),
            "tools_used": result.get("tools_used"),
            "steps": result.get("step_results"),
            "answer": result.get("final_answer"),
        },
        "trace": trace_result,
    }
