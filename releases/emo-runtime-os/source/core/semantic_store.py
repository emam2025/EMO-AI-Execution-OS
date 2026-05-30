"""Semantic Store – Phase 10.

FAISS-based vector store for symbol embeddings.

Architecture:
    EmbeddingEngine → SemanticStore → HybridRetriever

Supports:
    - upsert_symbol(symbol_id, vector, metadata)
    - remove_symbol(symbol_id)
    - search_similar(query_vector, top_k)

Design:
    - Local FAISS index (IndexIDMap over IndexFlatIP for cosine similarity)
    - Persisted on disk as a .faiss file + .json metadata
    - No external services required
    - Thread-safe via lock
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """Persistent FAISS vector store for code symbol embeddings.

    Usage:
        store = SemanticStore("/path/to/index/dir", dim=384)
        store.upsert_symbol("42", [0.1, 0.2, ...], {"name": "validate", ...})
        results = store.search_similar(query_vector, top_k=5)
    """

    def __init__(
        self,
        index_dir: str,
        dimension: int = 384,
    ):
        self._index_dir = Path(index_dir)
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._faiss_path = self._index_dir / "semantic.index"
        self._meta_path = self._index_dir / "semantic_meta.json"
        self._dim = dimension
        self._lock = threading.Lock()

        # In-memory metadata: symbol_id -> {name, file_id, ...}
        self._metadata: Dict[str, Dict[str, Any]] = {}

        if not _FAISS_AVAILABLE:
            logger.warning("FAISS not installed — SemanticStore is a no-op")
            self._index: Any = None
            return

        self._index = self._load_or_create()

    # ── public API ──────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return _FAISS_AVAILABLE and self._index is not None

    @property
    def size(self) -> int:
        if not self.available:
            return 0
        return self._index.ntotal

    def upsert_symbol(
        self,
        symbol_id: str,
        vector: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        """Insert or update a symbol embedding."""
        if not self.available or not vector:
            return
        with self._lock:
            vec = np.array([vector], dtype=np.float32)
            idx = self._int_id(symbol_id)

            # Remove existing entry if present (faiss IDMap allows remove)
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
        """Insert or update many symbols at once (efficient batched add)."""
        if not self.available or not vectors:
            return
        with self._lock:
            ids: List[int] = []
            vecs: List[np.ndarray] = []
            for sid, vec in vectors.items():
                ids.append(self._int_id(sid))
                vecs.append(np.array(vec, dtype=np.float32))
                self._metadata[sid] = metadata_map.get(sid, {})

            # Remove existing entries
            try:
                existing = np.array([self._int_id(s) for s in vectors if s in self._metadata])
                if len(existing):
                    self._index.remove_ids(existing)
            except Exception:
                pass

            self._index.add_with_ids(np.array(vecs), np.array(ids, dtype=np.int64))
            self._flush()

    def remove_symbol(self, symbol_id: str) -> None:
        """Delete a symbol embedding."""
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
        """Search for the *top_k* most similar symbols.

        Returns:
            List of dicts with keys: symbol_id, score, metadata.
        """
        if not self.available or self._index.ntotal == 0:
            return []
        with self._lock:
            q = np.array([query_vector], dtype=np.float32)
            k = min(top_k, self._index.ntotal)
            distances, indices = self._index.search(q, k)

        results: List[Dict[str, Any]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            sid = self._str_id(int(idx))
            meta = self._metadata.get(sid, {})
            # cosine similarity from inner product on normalized vectors
            score = float(dist)
            results.append({
                "symbol_id": sid,
                "score": round(score, 4),
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

        # Load metadata
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

    # ── id conversion ───────────────────────────────────────────────────

    @staticmethod
    def _int_id(symbol_id: str) -> int:
        """Deterministic int id from string id (FAISS IDs must be int64)."""
        # Use hash if the id is not a pure integer
        try:
            return int(symbol_id)
        except ValueError:
            return hash(symbol_id) & 0x7FFFFFFFFFFFFFFF

    @staticmethod
    def _str_id(int_id: int) -> str:
        """Reverse of _int_id — we can't recover the original string, so
        we look it up from metadata keys."""
        # We rely on the fact that _int_id is called consistently.
        # For lookups we just return the int as string; the caller
        # matches against metadata keys.
        return str(int_id)
