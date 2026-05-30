"""
Semantic Index — sqlite-vec wrapper with ANN/Exact search (LAW-6, LAW-11).

ISemanticIndex: protocol for vector indexing and similarity search.
Fallback implementation uses in-memory storage (prepared for sqlite-vec upgrade).
Every query enforces tenant_id/project_id isolation.
"""

from __future__ import annotations

import math
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from releases.memory_os.core.memory.embedding import cosine_similarity


class SemanticIndex:
    """Index for storing and searching embedding vectors.

    Current implementation: in-memory dict with brute-force cosine similarity.
    Designed as drop-in replacement for sqlite-vec ANN when available.
    Every insert/search enforces tenant_id isolation (LAW-6).
    """

    def __init__(self, dimensions: int = 8):
        self._dimensions = dimensions
        self._vectors: Dict[str, List[float]] = {}
        self._metadata: Dict[str, dict] = {}

    def init_index(self, dimensions: int) -> None:
        """Initialize/reconfigure the index with given dimensions."""
        self._dimensions = dimensions
        self._vectors.clear()
        self._metadata.clear()

    def insert(
        self,
        entry_id: str,
        vector: List[float],
        tenant_id: str,
        project_id: str = "",
        key: str = "",
        layer: str = "",
        created_at: float = 0.0,
    ) -> str:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not project_id:
            raise ValueError("project_id is required")
        if len(vector) != self._dimensions:
            raise ValueError(
                f"vector dimension {len(vector)} != index dimension {self._dimensions}"
            )
        self._vectors[entry_id] = list(vector)
        self._metadata[entry_id] = {
            "entry_id": entry_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "key": key,
            "layer": layer,
            "created_at": created_at,
        }
        return entry_id

    def search(
        self,
        query_vector: List[float],
        tenant_id: str,
        project_id: str = "",
        limit: int = 10,
        threshold: float = 0.0,
        scope: str = "project",
    ) -> List[dict]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        scored: List[Tuple[float, dict]] = []
        for eid, vec in self._vectors.items():
            meta = self._metadata.get(eid)
            if not meta or meta.get("tenant_id") != tenant_id:
                continue
            if scope == "project" and project_id and meta.get("project_id") != project_id:
                continue
            score = cosine_similarity(query_vector, vec)
            if score < threshold:
                continue
            scored.append((score, {**meta, "semantic_score": score}))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def delete(self, entry_id: str, tenant_id: str) -> bool:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        meta = self._metadata.get(entry_id)
        if not meta or meta.get("tenant_id") != tenant_id:
            return False
        self._vectors.pop(entry_id, None)
        self._metadata.pop(entry_id, None)
        return True

    def count(self, tenant_id: str) -> int:
        if not tenant_id:
            return 0
        return sum(1 for m in self._metadata.values() if m.get("tenant_id") == tenant_id)

    def clear(self) -> None:
        self._vectors.clear()
        self._metadata.clear()

    @property
    def dimensions(self) -> int:
        return self._dimensions
