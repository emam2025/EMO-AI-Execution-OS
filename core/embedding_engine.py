"""Embedding Engine – Phase 10 Semantic Retrieval.

Generates vector embeddings for symbols, files, and natural-language
queries using a lightweight local model (sentence-transformers).

Architecture:
    Indexer → EmbeddingEngine → SemanticStore (FAISS)
    Query   → EmbeddingEngine → HybridRetriever

Design:
    - Pure side-effect-free embedding (no mutation, no I/O beyond model load)
    - Model loaded lazily on first call
    - Configurable model name and device
    - Falls back cleanly if model unavailable
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.embedding")

_EMBEDDING_AVAILABLE: bool = False
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    _EMBEDDING_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    SentenceTransformer = None  # type: ignore[assignment]


# Default configuration
_DEFAULT_MODEL = "all-MiniLM-L6-v2"
_DEFAULT_CACHE = str(Path.home() / ".emo_ai" / "embedding_models")


class EmbeddingEngine:
    """Generates text embeddings using a local sentence-transformers model.

    Usage:
        ee = EmbeddingEngine()
        vec = ee.embed_text("def validate_email(email): ...")
        vec = ee.embed_symbol({"name": "validate_email", "signature": "validate_email(email)",
                                "docstring": "Check email format"})
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        cache_folder: str = _DEFAULT_CACHE,
        device: Optional[str] = None,
    ):
        self._model_name = model_name
        self._cache_folder = cache_folder
        self._device = device
        self._model: Optional[Any] = None  # lazy load

    # ── public API ──────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return _EMBEDDING_AVAILABLE

    @property
    def dimension(self) -> int:
        """Return the embedding dimension.  Loads the model if needed."""
        m = self._get_model()
        return m.get_sentence_embedding_dimension()

    def embed_text(self, text: str) -> List[float]:
        """Embed arbitrary text (query or source snippet)."""
        if not text.strip():
            return []
        m = self._get_model()
        vec = m.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def embed_symbol(self, symbol: Dict[str, Any]) -> List[float]:
        """Build and embed a rich text representation of a symbol."""
        text = self._symbol_to_text(symbol)
        return self.embed_text(text)

    def embed_file(self, file_dict: Dict[str, Any]) -> List[float]:
        """Embed a file-level description."""
        text = self._file_to_text(file_dict)
        return self.embed_text(text)

    def embed_batch(
        self, items: List[Dict[str, Any]], mode: str = "symbol"
    ) -> Dict[str, List[float]]:
        """Embed a batch of symbols/files.  Returns ``{identifier: vector}``."""
        if not self.available:
            return {}
        texts: List[str] = []
        ids: List[str] = []
        for item in items:
            if mode == "symbol":
                texts.append(self._symbol_to_text(item))
                ids.append(str(item.get("id", item.get("name", ""))))
            else:
                texts.append(self._file_to_text(item))
                ids.append(str(item.get("id", item.get("path", ""))))

        m = self._get_model()
        vecs = m.encode(texts, normalize_embeddings=True)
        return {i: vecs[idx].tolist() for idx, i in enumerate(ids)}

    # ── internal ────────────────────────────────────────────────────────

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not _EMBEDDING_AVAILABLE:
            raise RuntimeError(
                "sentence-transformers / torch not installed. "
                "Run: pip install sentence-transformers"
            )
        logger.info(
            "Loading embedding model '%s' (cache: %s) …",
            self._model_name, self._cache_folder,
        )
        self._model = SentenceTransformer(
            self._model_name,
            cache_folder=self._cache_folder,
            device=self._device,
        )
        logger.info("Model loaded, dim=%d", self._model.get_sentence_embedding_dimension())
        return self._model

    @staticmethod
    def _symbol_to_text(sym: Dict[str, Any]) -> str:
        """Build a searchable text snippet from a symbol dict."""
        parts: List[str] = []
        name = sym.get("name", sym.get("symbol_name", ""))
        parts.append(f"function: {name}")

        sig = sym.get("signature") or sym.get("symbol_id", "")
        if sig:
            parts.append(f"signature: {sig}")

        doc = sym.get("docstring", "")
        if doc:
            parts.append(f"docstring: {doc}")

        sym_type = sym.get("symbol_type", "function")
        parts.append(f"type: {sym_type}")

        decorators = sym.get("decorators", [])
        if decorators:
            parts.append(f"decorators: {', '.join(decorators)}")

        # Static analysis role
        props = sym.get("properties") or sym.get("static_analysis", {})
        if isinstance(props, dict):
            role = props.get("role", "")
            if role:
                parts.append(f"role: {role}")

        # Call context
        call_type = sym.get("call_type", "")
        if call_type:
            parts.append(f"call_type: {call_type}")

        return ". ".join(parts)

    @staticmethod
    def _file_to_text(fd: Dict[str, Any]) -> str:
        parts: List[str] = []
        parts.append(f"file: {fd.get('name', fd.get('path', ''))}")
        lang = fd.get("extension", "")
        if lang:
            parts.append(f"language: {lang.lstrip('.')}")
        symbols = fd.get("symbols", [])
        if symbols:
            names = [s.get("name", "") for s in symbols if s.get("name")]
            parts.append(f"contains: {', '.join(names[:10])}")
        return ". ".join(parts)
