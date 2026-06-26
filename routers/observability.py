"""Observability Dashboard — DAG visualization, replay UI, latency heatmap.

Serves an HTML dashboard that consumes the existing /api/ai/trace/* endpoints
for live DAG visualization, step-by-step replay, and node latency analysis.

Endpoints:
  GET /api/observability/  — Main dashboard HTML page
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from middleware.auth import require_auth

logger = logging.getLogger("emo_ai.router")

router = APIRouter(prefix="/api/observability", tags=["observability"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: dict = Depends(require_auth())):
    """Main observability dashboard."""
    return _templates.TemplateResponse(
        "observability.html",
        {"request": request},
    )
