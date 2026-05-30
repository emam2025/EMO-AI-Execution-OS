"""
Context Compression Engine — deduplication, graph-aware compression, ratio (LAW-6).

Deduplicates near-identical entries, compresses verbose payloads to graph-node summaries,
and calculates compression ratio. Target: ≥ 40% token reduction without critical data loss.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple

from releases.memory_os.core.memory.embedding import cosine_similarity


_DEDUP_SIMILARITY_THRESHOLD: float = 0.95


class CompressionEngine:
    """Compresses context windows via dedup and graph-aware summarization."""

    @staticmethod
    def deduplicate_context(entries: List[dict]) -> List[dict]:
        """Remove near-duplicate entries based on content hash + cosine similarity."""
        if not entries:
            return []
        unique: List[dict] = []
        seen_hashes: set = set()
        seen_vectors: List[Tuple[List[float], dict]] = []
        for e in entries:
            payload = e.get("payload", {})
            ph = CompressionEngine._payload_hash(payload)
            if ph in seen_hashes:
                continue
            seen_hashes.add(ph)
            vec = e.get("_embedding", None)
            if vec:
                is_dup = False
                for sv, _ in seen_vectors:
                    if cosine_similarity(vec, sv) >= _DEDUP_SIMILARITY_THRESHOLD:
                        is_dup = True
                        break
                if is_dup:
                    continue
                seen_vectors.append((vec, e))
            unique.append(e)
        return unique

    @staticmethod
    def compress_to_graph_nodes(entries: List[dict]) -> List[dict]:
        """Convert verbose payloads into concise graph-node-style summaries.

        Aims to reduce token count while preserving semantic meaning.
        """
        compressed: List[dict] = []
        for e in entries:
            payload = e.get("payload", {})
            if isinstance(payload, dict) and len(payload) > 2:
                summary = {}
                for k, v in payload.items():
                    sv = str(v)
                    if len(sv) > 100:
                        summary[k] = sv[:100] + "..."
                    else:
                        summary[k] = sv
                e["payload"] = summary
                e["_compressed"] = True
            else:
                e["_compressed"] = False
            compressed.append(e)
        return compressed

    @staticmethod
    def compress_text(text: str, max_chars: int = 200) -> str:
        """Truncate long text while preserving start and end context."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + "...[truncated]..." + text[-half:]

    @staticmethod
    def calculate_compression_ratio(original_tokens: int, compressed_tokens: int) -> float:
        """Calculate token reduction percentage."""
        if original_tokens <= 0:
            return 0.0
        ratio = (original_tokens - compressed_tokens) / original_tokens
        return max(0.0, ratio)

    @staticmethod
    def estimate_tokens(data: Any) -> int:
        """Rough token estimate for any JSON-serializable data."""
        raw = json.dumps(data, default=str)
        return max(1, len(raw) // 4)

    @staticmethod
    def _payload_hash(payload: dict) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
