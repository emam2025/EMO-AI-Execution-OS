"""
Memory Router — classification, scope selection, token budget allocation.

Routes queries to the correct memory hierarchy layer based on:
1. Query classification (project, agent, global)
2. Scope selection with tenant isolation
3. Token budget allocation per policy
LAW-6, LAW-11 enforced at every public method.
"""

from __future__ import annotations

import re
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from releases.memory_os.core.memory.context_selector import ContextSelector
from releases.memory_os.core.memory.enterprise_spaces import AgentMemorySpace, ProjectMemorySpace
from releases.memory_os.core.memory.governance import MemoryGovernanceEngine
from releases.memory_os.core.memory.graph_queries import GraphQueries
from releases.memory_os.core.memory.hierarchy import MemoryHierarchy
from releases.memory_os.core.memory.retrieval_ranker import RetrievalRanker
from releases.memory_os.core.memory.storage_adapter import SQLiteStorage
from releases.memory_os.core.models.memory import MemoryLayer, MemoryScope


class QueryClass(Enum):
    PROJECT = "project"
    AGENT = "agent"
    GLOBAL = "global"
    UNKNOWN = "unknown"


# ── keyword-based classification rules ───────────────────────

_PROJECT_KEYWORDS = [
    "project", "repo", "codebase", "feature", "bug", "task", "sprint",
    "readme", "documentation", "dependency", "module", "api",
]

_AGENT_KEYWORDS = [
    "agent", "session", "conversation", "user", "message", "chat",
    "instruction", "prompt", "response",
]

_GLOBAL_KEYWORDS = [
    "global", "all projects", "system", "config", "settings",
    "everywhere", "cross-project", "organization",
]


_BUDGET_TABLE: Dict[MemoryScope, int] = {
    MemoryScope.PROJECT: 4096,
    MemoryScope.AGENT: 2048,
    MemoryScope.GLOBAL: 1024,
}


class TokenBudgetExceeded(Exception):
    """Raised when a query exceeds its allocated token budget."""


class MemoryRouter:
    """Routes memory queries to the correct hierarchy layer.

    Responsibilities:
    - classify_query: keyword-based query classification
    - select_scope: resolve tenant/project/agent context
    - allocate_budget: compute token budget from scope + policy
    - route_and_retrieve: orchestrate full retrieval + ranking + selection pipeline
    """

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        tenant_id: str = "",
        project_id: str = "",
        agent_id: str = "",
        cognitive_trace_id: str = "",
        ranker: Optional[RetrievalRanker] = None,
        context_selector: Optional[ContextSelector] = None,
    ):
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        self._hierarchy = hierarchy
        self._tenant_id = tenant_id
        self._project_id = project_id
        self._agent_id = agent_id
        self._cognitive_trace_id = cognitive_trace_id
        self._ranker = ranker or RetrievalRanker()
        self._context_selector = context_selector or ContextSelector()

    # ── classification ──────────────────────────────────────────

    @staticmethod
    def classify_query(query: str) -> QueryClass:
        """Classify a query into project/agent/global based on keywords."""
        if not query or not query.strip():
            return QueryClass.UNKNOWN
        q_lower = query.lower().strip()
        score_project = sum(1 for kw in _PROJECT_KEYWORDS if kw in q_lower)
        score_agent = sum(1 for kw in _AGENT_KEYWORDS if kw in q_lower)
        score_global = sum(1 for kw in _GLOBAL_KEYWORDS if kw in q_lower)
        scores = {
            QueryClass.PROJECT: score_project,
            QueryClass.AGENT: score_agent,
            QueryClass.GLOBAL: score_global,
        }
        max_score = max(scores.values())
        tied = [k for k, v in scores.items() if v == max_score]
        if max_score == 0:
            return QueryClass.PROJECT
        priority = [QueryClass.PROJECT, QueryClass.AGENT, QueryClass.GLOBAL]
        for p in priority:
            if p in tied:
                return p
        return QueryClass.PROJECT

    # ── scope selection ─────────────────────────────────────────

    def select_scope(
        self,
        tenant_id: str,
        project_id: str,
        agent_id: str,
    ) -> Tuple[str, str, str]:
        """Validate and return the resolved scope identifiers."""
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        return (tenant_id, project_id or self._project_id, agent_id or self._agent_id)

    # ── budget allocation ───────────────────────────────────────

    @staticmethod
    def allocate_budget(query: str, scope: MemoryScope = MemoryScope.PROJECT, base: int = 4096) -> int:
        """Allocate token budget based on scope and query length."""
        base_budget = _BUDGET_TABLE.get(scope, base)
        query_length = len(query.split())
        if query_length > 50:
            base_budget = max(base_budget // 2, 256)
        elif query_length > 20:
            base_budget = int(base_budget * 0.8)
        return max(base_budget, 128)

    # ── main routing pipeline ───────────────────────────────────

    def route_and_retrieve(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        cognitive_trace_id: Optional[str] = None,
        limit: int = 10,
    ) -> dict:
        if tenant_id is not None and not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        tid = tenant_id or self._tenant_id
        pid = project_id or self._project_id
        aid = agent_id or self._agent_id
        ctid = cognitive_trace_id or self._cognitive_trace_id
        if not tid:
            raise ValueError("tenant_id is required (LAW-6)")
        qclass = self.classify_query(query)
        scope_map = {
            QueryClass.PROJECT: MemoryScope.PROJECT,
            QueryClass.AGENT: MemoryScope.AGENT,
            QueryClass.GLOBAL: MemoryScope.GLOBAL,
            QueryClass.UNKNOWN: MemoryScope.PROJECT,
        }
        scope = scope_map[qclass]
        token_budget = self.allocate_budget(query, scope)
        if token_budget < 128:
            raise TokenBudgetExceeded(
                f"token_budget={token_budget} below minimum threshold"
            )
        layers = [l.value for l in MemoryLayer]
        all_entries: List[dict] = []
        for layer in layers:
            q = {"scope": scope.value, "text": query, "semantic_threshold": 0.0, "token_budget": token_budget}
            results = self._hierarchy.retrieve(
                layer=layer,
                query=q,
                tenant_id=tid,
                project_id=pid,
                cognitive_trace_id=ctid,
                limit=min(limit, 5),
            )
            all_entries.extend(results)
        router_context = {
            "classification": qclass.value,
            "scope": scope.value,
            "tenant_id": tid,
            "project_id": pid,
        }
        ranked = self._ranker.rank_results(all_entries, router_context)
        selection = self._context_selector.select_context(
            query=query,
            budget=token_budget,
            ranked_results=ranked,
            tenant_id=tid,
            project_id=pid,
            cognitive_trace_id=ctid,
        )
        graph_context = {}
        if self._hierarchy.graph_store:
            gq = GraphQueries(self._hierarchy.graph_store)
            failure_patterns = gq.find_failure_patterns(tid, pid)
            graph_context = {
                "failure_patterns": failure_patterns,
                "total_nodes": self._hierarchy.graph_store.count_nodes(tid, pid),
            }
        return {
            "query": query,
            "classification": qclass.value,
            "scope": scope.value,
            "tenant_id": tid,
            "project_id": pid,
            "entries": ranked[:limit],
            "token_budget_allocated": token_budget,
            "tokens_used": selection["tokens_used"],
            "entries_returned": min(len(ranked), limit),
            "entries_selected_in_context": selection["entries_selected"],
            "sematic_enabled": self._hierarchy.semantic_index is not None,
            "graph_context": graph_context,
            "compression_enabled": self._hierarchy.compression_engine is not None,
            "filter_enabled": self._hierarchy.relevance_filter is not None,
            "optimizer_enabled": self._hierarchy.token_optimizer is not None,
        }

    @property
    def hierarchy(self) -> MemoryHierarchy:
        return self._hierarchy

    @property
    def ranker(self) -> RetrievalRanker:
        return self._ranker

    @property
    def context_selector(self) -> ContextSelector:
        return self._context_selector

    # ── enterprise space factory ──────────────────────────────

    def project_space(self, project_id: str, tenant_id: str) -> ProjectMemorySpace:
        return ProjectMemorySpace(self._hierarchy, project_id, tenant_id)

    def agent_space(self, agent_id: str, tenant_id: str, project_id: str = "") -> AgentMemorySpace:
        return AgentMemorySpace(self._hierarchy, agent_id, tenant_id, project_id)
