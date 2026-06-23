"""Tests for VectorDB — InMemoryVectorDB + factory."""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.vector_db import (
    InMemoryVectorDB,
    QdrantVectorDB,
    VectorDB,
    create_vector_db,
)
from abc import ABC


# ── VectorDB ABC ───────────────────────────────────────────────

def test_vector_db_is_abstract():
    assert issubclass(VectorDB, ABC)
    assert hasattr(VectorDB, "upsert")
    assert hasattr(VectorDB, "search")
    assert hasattr(VectorDB, "delete")
    assert hasattr(VectorDB, "count")
    assert hasattr(VectorDB, "clear")


# ── InMemoryVectorDB ──────────────────────────────────────────

def test_inmemory_upsert_and_search():
    db = InMemoryVectorDB()
    db.upsert("doc1", [1.0, 0.0, 0.0], {"text": "hello"})
    db.upsert("doc2", [0.0, 1.0, 0.0], {"text": "world"})
    db.upsert("doc3", [0.0, 0.0, 1.0], {"text": "foo"})
    assert db.count() == 3


def test_inmemory_search_returns_relevant():
    db = InMemoryVectorDB()
    db.upsert("a", [1.0, 0.0])
    db.upsert("b", [0.0, 1.0])
    results = db.search([1.0, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0]["point_id"] == "a"
    assert results[0]["score"] > 0.9


def test_inmemory_search_empty():
    db = InMemoryVectorDB()
    assert db.search([1.0, 0.0]) == []


def test_inmemory_delete():
    db = InMemoryVectorDB()
    db.upsert("x", [1.0, 0.0])
    assert db.count() == 1
    db.delete("x")
    assert db.count() == 0


def test_inmemory_clear():
    db = InMemoryVectorDB()
    db.upsert("a", [1.0, 0.0])
    db.upsert("b", [0.0, 1.0])
    db.clear()
    assert db.count() == 0


def test_inmemory_upsert_batch():
    db = InMemoryVectorDB()
    points = {"p1": [1.0, 0.0], "p2": [0.0, 1.0]}
    payloads = {"p1": {"tag": "first"}, "p2": {"tag": "second"}}
    db.upsert_batch(points, payloads)
    assert db.count() == 2
    results = db.search([1.0, 0.0])
    assert results[0]["payload"]["tag"] == "first"


def test_inmemory_payload_preserved():
    db = InMemoryVectorDB()
    db.upsert("doc", [0.5, 0.5], {"name": "test", "value": 42})
    results = db.search([0.5, 0.5])
    assert results[0]["payload"]["name"] == "test"
    assert results[0]["payload"]["value"] == 42


def test_inmemory_search_top_k():
    db = InMemoryVectorDB()
    for i in range(10):
        vec = [0.0] * 10
        vec[i] = 1.0
        db.upsert(f"dim{i}", vec)
    results = db.search([1.0] + [0.0] * 9, top_k=3)
    assert len(results) == 3


# ── create_vector_db factory ──────────────────────────────────

def test_create_inmemory_default():
    db = create_vector_db()
    assert isinstance(db, InMemoryVectorDB)


def test_create_qdrant_noop_when_missing():
    # Qdrant won't be available, so it should log a warning but not crash
    db = create_vector_db("qdrant")
    assert isinstance(db, QdrantVectorDB)
    # All operations should be no-ops without qdrant-client
    db.upsert("test", [1.0, 0.0])
    assert db.count() == 0
    assert db.search([1.0, 0.0]) == []
