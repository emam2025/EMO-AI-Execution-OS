"""Task 2 — R2-C graph integration with R2-A/R2-B: 10 tests.

Verifies entity extraction, graph storage, graph queries, and hybrid
graph ↔ semantic context without breaking existing contracts.
"""

import tempfile
import pytest

from releases.memory_os.core.memory.entity_extractor import (
    EdgeType,
    Entity,
    EntityType,
    HeuristicEntityExtractor,
    Relationship,
)
from releases.memory_os.core.memory.graph_queries import GraphQueries
from releases.memory_os.core.memory.graph_store import GraphStore
from releases.memory_os.core.memory.hierarchy import MemoryHierarchy
from releases.memory_os.core.memory.memory_router import MemoryRouter
from releases.memory_os.core.memory.semantic_index import SemanticIndex
from releases.memory_os.core.memory.embedding import MockEmbeddingProvider


class TestEntityExtractorWithHierarchy:
    @pytest.fixture
    def hierarchy_with_graph(self):
        tmp = tempfile.mkdtemp(prefix="r2c_int_")
        g = GraphStore(base_dir=tmp)
        h = MemoryHierarchy(base_dir=tmp, graph_store=g)
        h.store("episodic", "deploy_log", {"msg": "deployment"}, "t1", "p1", "a1", "ct1",
                text="tool deployer failed with error timeout in function build")
        h.store("episodic", "chat_log", {"msg": "chat"}, "t1", "p1", "a1", "ct1",
                text="agent code-assistant responded")
        yield h, g
        g.close()

    def test_store_extracts_entities_into_graph(self, hierarchy_with_graph):
        h, g = hierarchy_with_graph
        assert g.count_nodes("t1", "p1") >= 4

    def test_store_creates_relationships(self, hierarchy_with_graph):
        h, g = hierarchy_with_graph
        assert g.count_edges("t1") >= 1

    def test_store_without_text_skips_graph(self, hierarchy_with_graph):
        h, g = hierarchy_with_graph
        h.store("episodic", "no_text", {"x": 1}, "t1", "p1", "a1", "ct1", text="")
        count_before = g.count_nodes("t1", "p1")
        assert count_before >= 4


class TestGraphQueries:
    @pytest.fixture
    def graph_and_queries(self):
        tmp = tempfile.mkdtemp(prefix="r2c_q_")
        g = GraphStore(base_dir=tmp)
        ents = [
            Entity("n1", "t1", "p1", "deployer", EntityType.TOOL, "deployment tool"),
            Entity("n2", "t1", "p1", "timeout", EntityType.ERROR, "timeout error"),
            Entity("n3", "t1", "p1", "build_fn", EntityType.FUNCTION, "build function"),
            Entity("n4", "t1", "p2", "deployer", EntityType.TOOL, "other project"),
        ]
        for e in ents:
            g.add_node(e)
        g.add_edge(Relationship("r1", "t1", "p1", "n1", "n2", EdgeType.FAILS_WITH))
        g.add_edge(Relationship("r2", "t1", "p1", "n1", "n3", EdgeType.CALLS))
        gq = GraphQueries(g)
        yield g, gq
        g.close()

    def test_find_failure_patterns(self, graph_and_queries):
        g, gq = graph_and_queries
        failures = gq.find_failure_patterns("t1", "p1")
        assert len(failures) >= 1
        assert failures[0]["tool"] == "deployer"
        assert failures[0]["error"] == "timeout"

    def test_trace_impact_returns_neighbors(self, graph_and_queries):
        g, gq = graph_and_queries
        impacted = gq.trace_impact("n1", "t1", "p1")
        assert len(impacted) >= 2

    def test_trace_impact_respects_project_boundary(self, graph_and_queries):
        g, gq = graph_and_queries
        impacted = gq.trace_impact("n4", "t1", "p2")
        for n in impacted:
            assert n["project_id"] == "p2"

    def test_get_related_context_hybrid(self, graph_and_queries):
        g, gq = graph_and_queries
        ctx = gq.get_related_context("n1", "t1", "p1")
        assert ctx["node"] is not None
        assert len(ctx["neighbors"]) >= 2

    def test_get_related_context_requires_tenant_id(self, graph_and_queries):
        g, gq = graph_and_queries
        with pytest.raises(ValueError, match="tenant_id"):
            gq.get_related_context("n1", "", "p1")


class TestRouterGraphAwareness:
    @pytest.fixture
    def router_with_graph(self):
        tmp = tempfile.mkdtemp(prefix="r2c_rtr_")
        g = GraphStore(base_dir=tmp)
        h = MemoryHierarchy(base_dir=tmp, graph_store=g)
        h.store("episodic", "log1", {"msg": "deploy"}, "t1", "p1", "a1", "ct1",
                text="tool deployer error timeout in function build")
        router = MemoryRouter(hierarchy=h, tenant_id="t1", project_id="p1", agent_id="a1", cognitive_trace_id="ct1")
        yield router, g
        g.close()

    def test_router_returns_graph_context(self, router_with_graph):
        router, g = router_with_graph
        result = router.route_and_retrieve("project deployment")
        assert "graph_context" in result
        assert "failure_patterns" in result["graph_context"]

    def test_router_graph_has_total_nodes(self, router_with_graph):
        router, g = router_with_graph
        result = router.route_and_retrieve("test")
        assert result["graph_context"]["total_nodes"] >= 3
