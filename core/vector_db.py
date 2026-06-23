"""Vector DB abstraction — in-memory + Qdrant backends.

Environment:
    VECTOR_DB_URL       Qdrant gRPC URL (default: http://localhost:6333)
    VECTOR_DB_COLLECTION  Collection name (default: emo_vectors)
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.vector_db")

VECTOR_DB_URL = os.getenv("VECTOR_DB_URL", "http://localhost:6333")
VECTOR_DB_COLLECTION = os.getenv("VECTOR_DB_COLLECTION", "emo_vectors")


class VectorDB(ABC):
    """Abstract vector database for embedding storage and search."""

    @abstractmethod
    def upsert(self, point_id: str, vector: List[float], payload: Optional[Dict] = None) -> None:
        ...

    @abstractmethod
    def upsert_batch(self, points: Dict[str, List[float]], payloads: Optional[Dict[str, Dict]] = None) -> None:
        ...

    @abstractmethod
    def delete(self, point_id: str) -> None:
        ...

    @abstractmethod
    def search(self, query_vector: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...


class InMemoryVectorDB(VectorDB):
    """In-memory dict-based vector store (for testing / dev)."""

    def __init__(self):
        self._vectors: Dict[str, List[float]] = {}
        self._payloads: Dict[str, Dict] = {}

    def upsert(self, point_id: str, vector: List[float], payload: Optional[Dict] = None) -> None:
        self._vectors[point_id] = vector
        if payload:
            self._payloads[point_id] = payload

    def upsert_batch(self, points: Dict[str, List[float]], payloads: Optional[Dict[str, Dict]] = None) -> None:
        for pid, vec in points.items():
            self._vectors[pid] = vec
            if payloads and pid in payloads:
                self._payloads[pid] = payloads[pid]

    def delete(self, point_id: str) -> None:
        self._vectors.pop(point_id, None)
        self._payloads.pop(point_id, None)

    def search(self, query_vector: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        if not self._vectors:
            return []
        import math
        q = query_vector
        scored = []
        for pid, vec in self._vectors.items():
            dot = sum(a * b for a, b in zip(q, vec))
            norm_q = math.sqrt(sum(a * a for a in q))
            norm_v = math.sqrt(sum(a * a for a in vec))
            similarity = dot / (norm_q * norm_v) if norm_q and norm_v else 0.0
            scored.append((similarity, pid))
        scored.sort(key=lambda x: -x[0])
        results = []
        for score, pid in scored[:top_k]:
            results.append({
                "point_id": pid,
                "score": round(float(score), 4),
                "payload": self._payloads.get(pid, {}),
            })
        return results

    def count(self) -> int:
        return len(self._vectors)

    def clear(self) -> None:
        self._vectors.clear()
        self._payloads.clear()


class QdrantVectorDB(VectorDB):
    """Qdrant-based vector store (production)."""

    def __init__(self, url: str = VECTOR_DB_URL, collection: str = VECTOR_DB_COLLECTION, dimension: int = 384):
        self._url = url
        self._collection = collection
        self._dim = dimension
        self._client = None
        self._ensure_collection()

    def _client_or_none(self):
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models
            self._client = QdrantClient(url=self._url)
            self._models = models
            return self._client
        except ImportError:
            logger.warning("qdrant-client not installed — QdrantVectorDB is a no-op")
            return None

    def _ensure_collection(self):
        client = self._client_or_none()
        if client is None:
            return
        collections = client.get_collections().collections
        existing = {c.name for c in collections}
        if self._collection not in existing:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=self._models.VectorParams(
                    size=self._dim,
                    distance=self._models.Distance.COSINE,
                ),
            )

    def upsert(self, point_id: str, vector: List[float], payload: Optional[Dict] = None) -> None:
        client = self._client_or_none()
        if client is None:
            return
        client.upsert(
            collection_name=self._collection,
            points=[self._models.PointStruct(
                id=hash(point_id) & 0x7FFFFFFFFFFFFFFF,
                vector=vector,
                payload=payload or {},
            )],
        )

    def upsert_batch(self, points: Dict[str, List[float]], payloads: Optional[Dict[str, Dict]] = None) -> None:
        client = self._client_or_none()
        if client is None:
            return
        pts = []
        for pid, vec in points.items():
            pts.append(self._models.PointStruct(
                id=hash(pid) & 0x7FFFFFFFFFFFFFFF,
                vector=vec,
                payload=(payloads or {}).get(pid, {}),
            ))
        client.upsert(collection_name=self._collection, points=pts)

    def delete(self, point_id: str) -> None:
        client = self._client_or_none()
        if client is None:
            return
        client.delete(
            collection_name=self._collection,
            points_selector=self._models.Filter(
                must=[self._models.FieldCondition(
                    key="point_id",
                    match=self._models.MatchValue(value=point_id),
                )],
            ),
        )

    def search(self, query_vector: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        client = self._client_or_none()
        if client is None:
            return []
        hits = client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
        )
        results = []
        for hit in hits:
            results.append({
                "point_id": str(hit.id),
                "score": round(float(hit.score), 4),
                "payload": hit.payload or {},
            })
        return results

    def count(self) -> int:
        client = self._client_or_none()
        if client is None:
            return 0
        return client.count(collection_name=self._collection).count

    def clear(self) -> None:
        client = self._client_or_none()
        if client is None:
            return
        client.delete_collection(collection_name=self._collection)
        self._ensure_collection()


def create_vector_db(backend: str = "in_memory", **kwargs) -> VectorDB:
    """Factory — returns the appropriate VectorDB backend."""
    if backend == "qdrant":
        return QdrantVectorDB(**kwargs)
    logger.info("Using InMemoryVectorDB (backend=%s)", backend)
    return InMemoryVectorDB()
