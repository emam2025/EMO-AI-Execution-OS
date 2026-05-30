"""
Memory Hierarchy — IMemoryHierarchy implementation with tenant isolation.

Basic hierarchical storage + optional semantic indexing.
Layer-based scoped retrieval and TTL/LRU pruning.
LAW-6, LAW-11 enforced at every public method.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from releases.memory_os.core.memory.compression_engine import CompressionEngine
from releases.memory_os.core.memory.embedding import MockEmbeddingProvider
from releases.memory_os.core.memory.entity_extractor import HeuristicEntityExtractor
from releases.memory_os.core.memory.graph_store import GraphStore
from releases.memory_os.core.memory.relevance_filter import RelevanceFilter
from releases.memory_os.core.memory.semantic_index import SemanticIndex
from releases.memory_os.core.memory.storage_adapter import SQLiteStorage
from releases.memory_os.core.memory.token_optimizer import TokenOptimizer
from releases.memory_os.core.models.memory import (
    MemoryEntry,
    MemoryLayer,
    MemoryScope,
    PruningPolicy,
)


class MemoryHierarchy:
    """Concrete implementation of IMemoryHierarchy protocol.

    Uses SQLiteStorage for persistence with row-level tenant isolation.
    Optional SemanticIndex for embedding-based retrieval.
    Optional CompressionEngine, RelevanceFilter, TokenOptimizer for R2-D.
    """

    def __init__(
        self,
        storage: Optional[SQLiteStorage] = None,
        semantic_index: Optional[SemanticIndex] = None,
        embedding_provider: Optional[MockEmbeddingProvider] = None,
        graph_store: Optional[GraphStore] = None,
        entity_extractor: Optional[HeuristicEntityExtractor] = None,
        compression_engine: Optional[CompressionEngine] = None,
        relevance_filter: Optional[RelevanceFilter] = None,
        token_optimizer: Optional[TokenOptimizer] = None,
        base_dir: str = "/tmp/memory_os_data",
    ):
        self._storage = storage or SQLiteStorage(base_dir=base_dir)
        self._semantic_index = semantic_index
        self._embedding_provider = embedding_provider
        self._graph_store = graph_store
        self._entity_extractor = entity_extractor or HeuristicEntityExtractor()
        self._compression_engine = compression_engine
        self._relevance_filter = relevance_filter
        self._token_optimizer = token_optimizer

    # ── public API ──────────────────────────────────────────────

    def store(
        self,
        layer: str,
        key: str,
        payload: dict,
        tenant_id: str,
        project_id: str,
        agent_id: str,
        cognitive_trace_id: str,
        ttl_seconds: Optional[int] = None,
        scope: str = "project",
        text: str = "",
    ) -> dict:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not project_id:
            raise ValueError("project_id is required")
        mem_layer = MemoryLayer(layer) if isinstance(layer, str) else layer
        mem_scope = MemoryScope(scope) if isinstance(scope, str) else scope
        content_hash = self._content_hash(payload)
        created = time.time()
        entry = MemoryEntry(
            entry_id=f"mem-{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            project_id=project_id,
            agent_id=agent_id,
            layer=mem_layer,
            key=key,
            content_hash=content_hash,
            payload=payload,
            scope=mem_scope,
            ttl_seconds=ttl_seconds,
            created_at=created,
        )
        entry_id = self._storage.insert(entry)
        if self._semantic_index and self._embedding_provider and text:
            vec = self._embedding_provider.embed_text(text, tenant_id)
            self._semantic_index.insert(
                entry_id=entry_id,
                vector=vec,
                tenant_id=tenant_id,
                project_id=project_id,
                key=key,
                layer=layer,
                created_at=created,
            )
        if self._graph_store and text:
            entities = self._entity_extractor.extract_entities(text, tenant_id, project_id)
            for ent in entities:
                node_id = self._graph_store.add_node(ent)
            if len(entities) >= 2:
                rels = self._entity_extractor.map_relationships(entities, text, tenant_id, project_id)
                for rel in rels:
                    self._graph_store.add_edge(rel)
        return {"entry_id": entry_id, "stored": True, "layer": layer, "semantic_indexed": bool(text and self._semantic_index)}

    def retrieve(
        self,
        layer: str,
        query: dict,
        tenant_id: str,
        project_id: str,
        cognitive_trace_id: str,
        limit: int = 10,
    ) -> List[dict]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        mem_layer = MemoryLayer(layer) if isinstance(layer, str) else layer
        scope_str = query.get("scope", "project")
        key_filter = query.get("key")
        query_text = query.get("text", "")
        mem_scope = MemoryScope(scope_str)
        results = self._storage.select(
            tenant_id=tenant_id,
            project_id=project_id,
            scope=mem_scope,
            layer=mem_layer,
            limit=limit,
        )
        if key_filter:
            results = [r for r in results if r["key"] == key_filter]
        for r in results:
            r["payload"] = self._deserialize_payload(r.get("payload", "{}"))
            r["semantic_score"] = 0.0
        if query_text and self._semantic_index and self._embedding_provider:
            qvec = self._embedding_provider.embed_text(query_text, tenant_id)
            semantic_results = self._semantic_index.search(
                query_vector=qvec,
                tenant_id=tenant_id,
                project_id=project_id,
                limit=limit,
                threshold=query.get("semantic_threshold", 0.0),
                scope=scope_str,
            )
            semantic_map = {r["entry_id"]: r.get("semantic_score", 0.0) for r in semantic_results}
            for r in results:
                r["semantic_score"] = semantic_map.get(r["entry_id"], 0.0)
        if self._relevance_filter:
            results = self._relevance_filter.filter_low_relevance(results)
        if self._compression_engine:
            results = self._compression_engine.deduplicate_context(results)
            results = self._compression_engine.compress_to_graph_nodes(results)
        budget = query.get("token_budget", 0)
        if budget > 0 and self._token_optimizer:
            results, _ = self._token_optimizer.enforce_budget(results, budget)
        return results

    def prune(
        self,
        layer: str,
        policy: str,
        tenant_id: str,
        project_id: str,
        cognitive_trace_id: str,
        **kwargs: Any,
    ) -> dict:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if policy == PruningPolicy.TTL.value:
            removed = self._storage.delete_expired(tenant_id)
        elif policy == PruningPolicy.LRU.value:
            max_count = kwargs.get("max_entries", 10000)
            current_count = self._storage.count(tenant_id)
            removed = 0
            if current_count > max_count:
                excess = current_count - max_count
                removed = self._prune_oldest(tenant_id, layer, excess)
        else:
            removed = self._storage.delete_expired(tenant_id)
        return {"entries_removed": removed, "layer": layer, "policy": policy}

    def get_context_window(
        self,
        tenant_id: str,
        project_id: str,
        cognitive_trace_id: str,
        window_size: int = 10,
        layers: Optional[List[str]] = None,
    ) -> dict:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not project_id:
            raise ValueError("project_id is required")
        layer_list = layers or [l.value for l in MemoryLayer]
        entries: dict = {}
        for l in layer_list:
            results = self._storage.select(
                tenant_id=tenant_id,
                project_id=project_id,
                scope=MemoryScope.PROJECT,
                layer=MemoryLayer(l),
                limit=window_size,
            )
            for r in results:
                r["payload"] = self._deserialize_payload(r.get("payload", "{}"))
            entries[l] = results
        return {"entries": entries, "window_size": window_size, "tenant_id": tenant_id}

    # ── helpers ──────────────────────────────────────────────────

    def _prune_oldest(self, tenant_id: str, layer: str, count: int) -> int:
        results = self._storage.select(
            tenant_id=tenant_id,
            project_id="",
            scope=MemoryScope.GLOBAL,
            layer=MemoryLayer(layer),
            limit=count,
        )
        removed = 0
        for r in results:
            if self._storage.delete(r["entry_id"], tenant_id):
                if self._semantic_index:
                    self._semantic_index.delete(r["entry_id"], tenant_id)
                removed += 1
        return removed

    @staticmethod
    def _content_hash(payload: dict) -> str:
        import hashlib, json
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _deserialize_payload(raw: str) -> dict:
        import json
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return {}

    # ── enterprise space factories ─────────────────────────────

    def project_space(self, project_id: str, tenant_id: str):
        from releases.memory_os.core.memory.enterprise_spaces import ProjectMemorySpace
        return ProjectMemorySpace(self, project_id, tenant_id)

    def agent_space(self, agent_id: str, tenant_id: str, project_id: str = ""):
        from releases.memory_os.core.memory.enterprise_spaces import AgentMemorySpace
        return AgentMemorySpace(self, agent_id, tenant_id, project_id)

    @property
    def storage(self) -> SQLiteStorage:
        return self._storage

    @property
    def semantic_index(self) -> Optional[SemanticIndex]:
        return self._semantic_index

    @property
    def embedding_provider(self) -> Optional[MockEmbeddingProvider]:
        return self._embedding_provider

    @property
    def graph_store(self) -> Optional[GraphStore]:
        return self._graph_store

    @property
    def compression_engine(self) -> Optional[CompressionEngine]:
        return self._compression_engine

    @property
    def relevance_filter(self) -> Optional[RelevanceFilter]:
        return self._relevance_filter

    @property
    def token_optimizer(self) -> Optional[TokenOptimizer]:
        return self._token_optimizer
