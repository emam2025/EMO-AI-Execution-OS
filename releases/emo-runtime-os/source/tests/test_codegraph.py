"""Tests for CodeGraph v1 — deterministic static analysis + graph compilation."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.codegraph import (
    CodeGraph,
    CodeGraphQueryEngine,
    Edge,
    EdgeType,
    Node,
    NodeType,
    build_codegraph,
    load,
    save,
    to_llm_context,
)
from core.codegraph.determinism import make_node_id, stable_hash, sort_files
from core.codegraph.parser import ParsedFile, discover_files, parse_file


# ── Graph Model ──────────────────────────────────────────────────────────────


def test_node_creation():
    nid = make_node_id("core/foo.py", "FILE", "foo.py")
    node = Node(id=nid, type=NodeType.FILE, name="foo.py", path="core/foo.py")
    assert node.id == nid
    assert node.type == NodeType.FILE
    assert node.name == "foo.py"


def test_edge_hashable():
    e1 = Edge(from_id="a", to_id="b", type=EdgeType.IMPORTS)
    e2 = Edge(from_id="a", to_id="b", type=EdgeType.IMPORTS)
    s = {e1, e2}
    assert len(s) == 1  # dedup works


def test_codegraph_add():
    g = CodeGraph()
    nid = make_node_id("test.py", "FILE", "test.py")
    g.add_node(Node(id=nid, type=NodeType.FILE, name="test.py", path="test.py"))
    g.add_edge(Edge(from_id=nid, to_id="b", type=EdgeType.DEPENDS_ON))
    assert len(g.nodes) == 1
    assert len(g.edges) == 1
    assert g.checksum == ""


def test_codegraph_to_dict():
    g = CodeGraph(version="v1", checksum="abc")
    nid = make_node_id("x.py", "FILE", "x.py")
    g.add_node(Node(
        id=nid, type=NodeType.FILE, name="x.py", path="x.py",
        complexity_score=1.0, risk_score=0.5,
    ))
    g.add_edge(Edge(from_id=nid, to_id="y", type=EdgeType.IMPORTS))
    d = g.to_dict()
    assert d["version"] == "v1"
    assert d["checksum"] == "abc"
    assert nid in d["nodes"]
    assert len(d["edges"]) == 1


# ── Determinism ──────────────────────────────────────────────────────────────


def test_node_id_deterministic():
    id1 = make_node_id("a.py", "FILE", "a.py")
    id2 = make_node_id("a.py", "FILE", "a.py")
    assert id1 == id2


def test_node_id_different_path():
    id1 = make_node_id("a.py", "FILE", "a.py")
    id2 = make_node_id("b.py", "FILE", "a.py")
    assert id1 != id2


def test_node_id_hex_length():
    nid = make_node_id("x.py", "FILE", "x.py")
    assert len(nid) == 16
    assert all(c in "0123456789abcdef" for c in nid)


def test_stable_hash_deterministic():
    assert stable_hash("hello") == stable_hash("hello")


def test_sort_files():
    unsorted = ["z.py", "a.py", "m.py"]
    assert sort_files(unsorted) == ["a.py", "m.py", "z.py"]


# ── Parser ───────────────────────────────────────────────────────────────────


def test_discover_files():
    files = discover_files("core")
    assert len(files) > 0
    assert all(f.endswith(".py") for f in files)
    assert files == sorted(files)  # already sorted


def test_parse_python_file():
    parsed = parse_file("core/execution_engine.py")
    assert len(parsed.raw_imports) > 0
    assert len(parsed.classes) >= 1
    assert len(parsed.functions) >= 1


def test_parse_file_not_found():
    parsed = parse_file("/nonexistent/file.py")
    assert parsed.raw_imports == []


def test_parse_doc_file():
    # MD files are not source — regex may pick up code blocks
    parsed = parse_file("DEVELOPER.md")
    # Should have no AST-parsed classes/functions (not Python)
    assert len(parsed.classes) == 0
    assert len(parsed.functions) == 0


# ── Builder ──────────────────────────────────────────────────────────────────


def test_build_codegraph_deterministic():
    g1 = build_codegraph("core", include_docs=False)
    g2 = build_codegraph("core", include_docs=False)
    assert g1.checksum == g2.checksum
    assert len(g1.nodes) == len(g2.nodes)
    assert len(g1.edges) == len(g2.edges)


def test_build_codegraph_has_file_nodes():
    g = build_codegraph("core", include_docs=False)
    file_nodes = [n for n in g.nodes.values() if n.type == NodeType.FILE]
    assert len(file_nodes) > 0


def test_build_codegraph_edges():
    g = build_codegraph("core", include_docs=False)
    assert len(g.edges) > 0


def test_build_codegraph_with_docs():
    g = build_codegraph(".", include_docs=True)
    # Should include DEVELOPER.md and CHANGELOG.md
    md_nodes = [n for n in g.nodes.values() if n.path.endswith(".md")]
    assert len(md_nodes) > 0


# ── Query Engine ─────────────────────────────────────────────────────────────


def test_query_dependencies():
    g = build_codegraph("core", include_docs=False)
    qe = CodeGraphQueryEngine(g)
    ee = next(
        (n for n in g.nodes.values()
         if n.path.endswith("execution_engine.py") and n.type == NodeType.FILE),
        None,
    )
    if ee:
        deps = qe.get_dependencies(ee.path)
        assert len(deps) > 0


def test_query_dependents():
    g = build_codegraph("core", include_docs=False)
    qe = CodeGraphQueryEngine(g)
    # cost_intel should have at least execution_engine as dependent
    ci = next(
        (n for n in g.nodes.values()
         if n.path.endswith("cost_intel.py") and n.type == NodeType.FILE),
        None,
    )
    if ci:
        deps = qe.get_dependents(ci.path)
        assert len(deps) > 0


def test_execution_boundary():
    g = build_codegraph("core", include_docs=False)
    qe = CodeGraphQueryEngine(g)
    ee = next(
        (n for n in g.nodes.values()
         if n.path.endswith("execution_engine.py") and n.type == NodeType.FILE),
        None,
    )
    if ee:
        bound = qe.get_execution_boundary(ee.path)
        assert "entry_points" in bound
        assert "exit_points" in bound
        assert "isolated" in bound


def test_risk_profile():
    g = build_codegraph("core", include_docs=False)
    qe = CodeGraphQueryEngine(g)
    ee = next(
        (n for n in g.nodes.values()
         if n.path.endswith("execution_engine.py") and n.type == NodeType.FILE),
        None,
    )
    if ee:
        profile = qe.get_risk_profile(ee.path)
        assert "risk_score" in profile
        assert "complexity_score" in profile


# ── Serializer ───────────────────────────────────────────────────────────────


def test_llm_context_format():
    g = build_codegraph("core", include_docs=False)
    ctx = to_llm_context(g, max_nodes=3)
    assert "# CodeGraph" in ctx
    assert "[FILE]" in ctx
    assert "path:" in ctx


# ── Storage ──────────────────────────────────────────────────────────────────


def test_save_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        g = build_codegraph("core", include_docs=False)
        out = save(g, output_dir=os.path.join(tmp, "cg"))
        assert os.path.isdir(out)
        loaded = load(out)
        assert loaded.version == g.version
        assert loaded.checksum == g.checksum
        assert len(loaded.nodes) == len(g.nodes)


def test_load_nonexistent():
    with pytest.raises(FileNotFoundError):
        load("/nonexistent/codegraph")


# ── Integration ──────────────────────────────────────────────────────────────


def test_full_pipeline():
    g = build_codegraph("core", include_docs=True)
    assert len(g.nodes) > 0
    assert g.checksum != ""
    assert g.version == "v1"
    assert len(g.sorted_edges()) > 0

    qe = CodeGraphQueryEngine(g)
    for node in list(g.nodes.values())[:5]:
        profile = qe.get_risk_profile(node.path)
        assert profile is not None
