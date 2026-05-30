"""
Embedding Provider — unified interface for vector generation (LAW-6, LAW-11).

IEmbeddingProvider: protocol for generating and normalizing embeddings.
Supports mock (testing), local (sentence-transformers ready), and remote (API ready).
Zero external dependencies in mock mode.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IEmbeddingProvider(Protocol):
    """Protocol for embedding generation with tenant isolation."""

    def embed_text(self, text: str, tenant_id: str = "") -> List[float]:
        """Generate embedding vector for the given text."""
        ...

    def normalize_vector(self, vector: List[float]) -> List[float]:
        """Normalize vector to unit length (compatible with sqlite-vec)."""
        ...

    @property
    def dimensions(self) -> int:
        """Return the embedding dimension."""
        ...


class MockEmbeddingProvider:
    """Deterministic mock embedding provider for testing.

    Produces reproducible vectors based on text hash.
    Dimension: 8 (small for fast tests).
    """

    def __init__(self, dimensions: int = 8):
        self._dimensions = dimensions

    def embed_text(self, text: str, tenant_id: str = "") -> List[float]:
        if not text:
            return [0.0] * self._dimensions
        raw = hashlib.sha256((tenant_id + ":" + text).encode()).digest()
        vec = [(raw[i % len(raw)] / 255.0) * 2 - 1 for i in range(self._dimensions)]
        return self.normalize_vector(vec)

    def normalize_vector(self, vector: List[float]) -> List[float]:
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return [0.0] * len(vector)
        return [v / norm for v in vector]

    @property
    def dimensions(self) -> int:
        return self._dimensions


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(av * bv for av, bv in zip(a, b))
    norm_a = math.sqrt(sum(av * av for av in a))
    norm_b = math.sqrt(sum(bv * bv for bv in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
