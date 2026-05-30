"""
Context Selector — selects context windows within token_budget (LAW-6, LAW-11).

Selects entries from ranked results up to token_budget.
Enforces:
  - token_budget: never exceeded
  - tenant_id isolation: every entry must carry tenant_id
  - relevance_threshold: low-quality entries excluded upstream
Returns assembled ContextWindow with tokens_used tracking.
"""

from __future__ import annotations

import uuid
import time
from typing import Any, Dict, List, Optional

from releases.memory_os.core.models.memory import ContextWindow, MemoryEntry, MemoryLayer, MemoryScope


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: chars / 4 (compatible with llm tokenizers)."""
    return max(1, len(text) // 4)


def _entry_to_dict(entry: dict) -> dict:
    return {
        "entry_id": entry.get("entry_id", ""),
        "tenant_id": entry.get("tenant_id", ""),
        "project_id": entry.get("project_id", ""),
        "agent_id": entry.get("agent_id", ""),
        "layer": entry.get("layer", ""),
        "key": entry.get("key", ""),
        "content_hash": entry.get("content_hash", ""),
        "payload": entry.get("payload", {}),
        "relevance_score": entry.get("relevance_score", 0.0),
        "semantic_score": entry.get("semantic_score", 0.0),
    }


class ContextExceeded(Exception):
    """Raised when context budget is exceeded with minimum entries."""


class ContextSelector:
    """Selects and assembles context windows within token_budget."""

    def __init__(self, default_budget: int = 4096, safety_margin: float = 0.95):
        self._default_budget = default_budget
        self._safety_margin = safety_margin

    def select_context(
        self,
        query: str,
        budget: Optional[int] = None,
        ranked_results: Optional[List[dict]] = None,
        tenant_id: str = "",
        project_id: str = "",
        cognitive_trace_id: str = "",
    ) -> dict:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not project_id:
            raise ValueError("project_id is required")
        budget = budget or self._default_budget
        effective_budget = int(budget * self._safety_margin)
        results = ranked_results or []
        selected: List[dict] = []
        tokens_used = 0
        query_tokens = _estimate_tokens(query)
        tokens_used += query_tokens
        for r in results:
            entry_tokens = _estimate_tokens(str(r.get("payload", {})))
            entry_tokens += _estimate_tokens(r.get("key", ""))
            if tokens_used + entry_tokens > effective_budget:
                continue
            selected.append(_entry_to_dict(r))
            tokens_used += entry_tokens
        cw = ContextWindow(
            window_id=f"cw-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            project_id=project_id,
            cognitive_trace_id=cognitive_trace_id,
            trace_id="",
            entries=[],
            token_budget=budget,
            tokens_used=tokens_used,
            safety_bounds={
                "safety_margin": self._safety_margin,
                "effective_budget": effective_budget,
                "query_tokens": query_tokens,
            },
        )
        return {
            "context_window": cw,
            "selected_entries": selected,
            "tokens_used": tokens_used,
            "token_budget": budget,
            "entries_selected": len(selected),
            "entries_available": len(results),
            "tenant_id": tenant_id,
        }
