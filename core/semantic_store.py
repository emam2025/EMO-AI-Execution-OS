"""Semantic Store – Phase 10.

FAISS-based vector store for symbol embeddings.
Can optionally use VectorDB as backend instead of FAISS.

Architecture:
    EmbeddingEngine → SemanticStore → HybridRetriever

Supports:
    - upsert_symbol(symbol_id, vector, metadata)
    - remove_symbol(symbol_id)
    - search_similar(query_vector, top_k)
    - Optional VectorDB backend (InMemoryVectorDB / QdrantVectorDB)

Design:
    - Default: Local FAISS index (IndexIDMap over IndexFlatIP for cosine similarity)
    - Optional: VectorDB abstraction (in-memory or Qdrant)
    - Thread-safe via lock
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.vector_db import VectorDB

logger = logging.getLogger("emo_ai.semantic_store")

try:
    import faiss
    import numpy as np

    _FAISS_AVAILABLE = True
except ImportError:
    faiss = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    _FAISS_AVAILABLE = False


class SemanticStore:
    """Persistent vector store for code symbol embeddings.

    Uses FAISS by default, or accepts a VectorDB backend.

    Usage:
        store = SemanticStore("/path/to/index/dir", dim=384)
        store.upsert_symbol("42", [0.1, 0.2, ...], {"name": "validate", ...})
        results = store.search_similar(query_vector, top_k=5)
    """

    def __init__(
        self,
        index_dir: str,
        dimension: int = 384,
        backend: Optional[VectorDB] = None,
    ):
        self._index_dir = Path(index_dir)
        self._dim = dimension
        self._lock = threading.Lock()
        self._backend = backend

        self._metadata: Dict[str, Dict[str, Any]] = {}

        if backend is not None:
            self._faiss_path = None
            self._meta_path = None
            self._index: Any = None
            return

        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._faiss_path = self._index_dir / "semantic.index"
        self._meta_path = self._index_dir / "semantic_meta.json"

        if not _FAISS_AVAILABLE:
            logger.warning("FAISS not installed — SemanticStore is a no-op")
            self._index = None
            return

        self._index = self._load_or_create()

    # ── public API ──────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        if self._backend is not None:
            return True
        return _FAISS_AVAILABLE and self._index is not None

    @property
    def size(self) -> int:
        if self._backend is not None:
            return self._backend.count()
        if not self.available:
            return 0
        return self._index.ntotal

    def upsert_symbol(
        self,
        symbol_id: str,
        vector: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        if self._backend is not None:
            self._backend.upsert(symbol_id, vector, metadata)
            return
        if not self.available or not vector:
            return
        with self._lock:
            vec = np.array([vector], dtype=np.float32)
            idx = self._int_id(symbol_id)
            try:
                self._index.remove_ids(np.array([idx]))
            except Exception:
                pass
            self._index.add_with_ids(vec, np.array([idx]))
            self._metadata[symbol_id] = metadata
            self._flush()

    def upsert_batch(
        self,
        vectors: Dict[str, List[float]],
        metadata_map: Dict[str, Dict[str, Any]],
    ) -> None:
        if self._backend is not None:
            self._backend.upsert_batch(vectors, metadata_map)
            return
        if not self.available or not vectors:
            return
        with self._lock:
            ids: List[int] = []
            vecs: List[np.ndarray] = []
            for sid, vec in vectors.items():
                ids.append(self._int_id(sid))
                vecs.append(np.array(vec, dtype=np.float32))
                self._metadata[sid] = metadata_map.get(sid, {})
            try:
                existing = np.array([self._int_id(s) for s in vectors if s in self._metadata])
                if len(existing):
                    self._index.remove_ids(existing)
            except Exception:
                pass
            self._index.add_with_ids(np.array(vecs), np.array(ids, dtype=np.int64))
            self._flush()

    def remove_symbol(self, symbol_id: str) -> None:
        if self._backend is not None:
            self._backend.delete(symbol_id)
            return
        if not self.available:
            return
        with self._lock:
            try:
                self._index.remove_ids(np.array([self._int_id(symbol_id)]))
            except Exception:
                pass
            self._metadata.pop(symbol_id, None)
            self._flush()

    def search_similar(
        self,
        query_vector: List[float],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        if self._backend is not None:
            raw = self._backend.search(query_vector, top_k)
            results: List[Dict[str, Any]] = []
            for r in raw:
                results.append({
                    "symbol_id": r.get("point_id", ""),
                    "score": r.get("score", 0.0),
                    "metadata": r.get("payload", {}),
                })
            return results
        if not self.available or self._index.ntotal == 0:
            return []
        with self._lock:
            q = np.array([query_vector], dtype=np.float32)
            k = min(top_k, self._index.ntotal)
            distances, indices = self._index.search(q, k)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            sid = self._str_id(int(idx))
            meta = self._metadata.get(sid, {})
            results.append({
                "symbol_id": sid,
                "score": round(float(dist), 4),
                "metadata": meta,
            })
        return results

    # ── persistence ─────────────────────────────────────────────────────

    def _load_or_create(self) -> Any:
        if self._faiss_path.exists():
            try:
                idx = faiss.read_index(str(self._faiss_path))
                logger.info("Loaded FAISS index from %s (%d vectors)", self._faiss_path, idx.ntotal)
            except Exception:
                logger.warning("Corrupt index, re-creating")
                idx = self._create_index()
        else:
            idx = self._create_index()
        if self._meta_path.exists():
            try:
                with open(self._meta_path) as f:
                    self._metadata = json.load(f)
            except Exception:
                self._metadata = {}
        return idx

    def _create_index(self) -> Any:
        logger.info("Creating FAISS index (dim=%d)", self._dim)
        return faiss.IndexIDMap(faiss.IndexFlatIP(self._dim))

    def _flush(self) -> None:
        try:
            faiss.write_index(self._index, str(self._faiss_path))
            with open(self._meta_path, "w") as f:
                json.dump(self._metadata, f)
        except Exception as e:
            logger.error("Failed to persist FAISS index: %s", e)

    @staticmethod
    def _int_id(symbol_id: str) -> int:
        try:
            return int(symbol_id)
        except ValueError:
            return hash(symbol_id) & 0x7FFFFFFFFFFFFFFF

    @staticmethod
    def _str_id(int_id: int) -> str:
        return str(int_id)
