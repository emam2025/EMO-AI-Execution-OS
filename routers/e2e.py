"""E2E Pipeline Router — Full-Chain Integration Endpoint.

Runs the complete AI pipeline against a target repository:
  index -> graph -> semantic -> hybrid -> DAG execution -> replay -> telemetry

Endpoint:
  POST /api/e2e/pipeline — Execute the full pipeline
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from core.runtime.e2e_pipeline import build_e2e_components, run_e2e_pipeline
from core.composition.root import build_minimal_runtime

logger = logging.getLogger("emo_ai.router")

router = APIRouter(prefix="/api/e2e", tags=["e2e"])


@router.post("/pipeline")
def run_pipeline(
    repo_path: str,
    query: str,
    force_reindex: bool = False,
    include_trace: bool = True,
    runtime: Optional["UnifiedRuntime"] = None,
):
    """Execute the full AI pipeline: index -> graph -> semantic -> DAG -> trace.

    Args:
        repo_path: Absolute path to the target repository.
        query: Natural-language query about the codebase.
        force_reindex: If true, re-index all files regardless of changes.
        include_trace: If true, include DAG trace and replay in response.
    """
    try:
        result = run_e2e_pipeline(
            repo_path=repo_path,
            query=query,
            force_reindex=force_reindex,
            include_trace=include_trace,
            runtime=runtime,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("E2E pipeline failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
