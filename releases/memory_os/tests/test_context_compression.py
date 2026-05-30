"""Task 1 — Context Compression: 10 tests.

Verifies dedup, graph-aware compression, ratio calculation, semantic integrity.
"""

import pytest

from releases.memory_os.core.memory.compression_engine import CompressionEngine


class TestDeduplication:
    def test_identical_payloads_deduplicated(self):
        entries = [
            {"entry_id": "e1", "payload": {"msg": "hello"}, "key": "k1"},
            {"entry_id": "e2", "payload": {"msg": "hello"}, "key": "k1"},
        ]
        result = CompressionEngine.deduplicate_context(entries)
        assert len(result) == 1

    def test_different_payloads_kept(self):
        entries = [
            {"entry_id": "e1", "payload": {"msg": "hello"}, "key": "k1"},
            {"entry_id": "e2", "payload": {"msg": "world"}, "key": "k2"},
        ]
        result = CompressionEngine.deduplicate_context(entries)
        assert len(result) == 2

    def test_empty_list_returns_empty(self):
        assert CompressionEngine.deduplicate_context([]) == []

    def test_near_identical_vectors_deduplicated(self):
        entries = [
            {"entry_id": "e1", "payload": {"msg": "a"}, "key": "k1", "_embedding": [1.0, 0.0, 0.0]},
            {"entry_id": "e2", "payload": {"msg": "b"}, "key": "k2", "_embedding": [0.99, 0.01, 0.0]},
        ]
        result = CompressionEngine.deduplicate_context(entries)
        assert len(result) == 1


class TestGraphCompression:
    def test_large_payload_truncated(self):
        entries = [
            {"entry_id": "e1", "payload": {"a": "1", "b": "2", "c": "3", "long_field": "x" * 500}, "key": "k1"},
        ]
        result = CompressionEngine.compress_to_graph_nodes(entries)
        assert result[0]["_compressed"] is True
        assert len(result[0]["payload"]["long_field"]) < 200

    def test_small_payload_not_compressed(self):
        entries = [
            {"entry_id": "e1", "payload": {"msg": "hi"}, "key": "k1"},
        ]
        result = CompressionEngine.compress_to_graph_nodes(entries)
        assert result[0]["_compressed"] is False
        assert result[0]["payload"]["msg"] == "hi"

    def test_text_truncation_preserves_ends(self):
        text = "A" * 50 + "B" * 200 + "C" * 50
        compressed = CompressionEngine.compress_text(text, max_chars=120)
        assert compressed.startswith("A" * 50)
        assert compressed.endswith("C" * 50)
        assert len(compressed) < len(text)


class TestCompressionRatio:
    def test_ratio_zero_for_empty(self):
        assert CompressionEngine.calculate_compression_ratio(0, 0) == 0.0

    def test_ratio_fifty_percent(self):
        ratio = CompressionEngine.calculate_compression_ratio(100, 50)
        assert ratio == 0.5

    def test_ratio_meets_target(self):
        ratio = CompressionEngine.calculate_compression_ratio(1000, 500)
        assert ratio >= 0.4

    def test_ratio_never_negative(self):
        ratio = CompressionEngine.calculate_compression_ratio(50, 100)
        assert ratio == 0.0
