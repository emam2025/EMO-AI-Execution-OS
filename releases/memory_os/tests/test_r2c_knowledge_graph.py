"""Task 3 — Knowledge Graph: 15 tests.

Suites:
  TestEntityExtractionConsistency   (5)
  TestRelationshipMappingAccuracy   (5)
  TestGraphTraversalIsolation       (5)
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


# ── TestEntityExtractionConsistency (5) ──────────────────────

class TestEntityExtractionConsistency:
    @pytest.fixture
    def extractor(self):
        return HeuristicEntityExtractor()

    def test_same_text_produces_same_entities(self, extractor):
        e1 = extractor.extract_entities("tool api-gateway failed with error timeout", "t1", "p1")
        e2 = extractor.extract_entities("tool api-gateway failed with error timeout", "t1", "p1")
        names1 = sorted(e.name for e in e1)
        names2 = sorted(e.name for e in e2)
        assert names1 == names2

    def test_extracts_tool_entity(self, extractor):
        entities = extractor.extract_entities("tool deploy-service crashed", "t1", "p1")
        tools = [e for e in entities if e.entity_type == EntityType.TOOL]
        assert len(tools) >= 1
        assert "deploy-service" in [t.name for t in tools]

    def test_extracts_error_entity(self, extractor):
        entities = extractor.extract_entities("error timeout in api request", "t1", "p1")
        errors = [e for e in entities if e.entity_type == EntityType.ERROR]
        assert len(errors) >= 1
        assert "timeout" in [e.name for e in errors]

    def test_extracts_agent_entity(self, extractor):
        entities = extractor.extract_entities("agent code-assistant responded", "t1", "p1")
        agents = [e for e in entities if e.entity_type == EntityType.AGENT]
        assert len(agents) >= 1

    def test_empty_text_returns_no_entities(self, extractor):
        entities = extractor.extract_entities("", "t1", "p1")
        assert len(entities) == 0


# ── TestRelationshipMappingAccuracy (5) ──────────────────────

class TestRelationshipMappingAccuracy:
    @pytest.fixture
    def extractor(self):
        return HeuristicEntityExtractor()

    def test_tool_to_function_is_calls_edge(self, extractor):
        text = "tool deployer calls function build_image"
        entities = extractor.extract_entities(text, "t1", "p1")
        rels = extractor.map_relationships(entities, text, "t1", "p1")
        calls = [r for r in rels if r.edge_type == EdgeType.CALLS]
        assert len(calls) >= 1

    def test_error_edge_is_fails_with(self, extractor):
        text = "error timeout in function validate"
        entities = extractor.extract_entities(text, "t1", "p1")
        rels = extractor.map_relationships(entities, text, "t1", "p1")
        fails = [r for r in rels if r.edge_type == EdgeType.FAILS_WITH]
        assert len(fails) >= 1

    def test_all_relationships_have_tenant_id(self, extractor):
        text = "tool deployer error timeout"
        entities = extractor.extract_entities(text, "t1", "p1")
        rels = extractor.map_relationships(entities, text, "t1", "p1")
        for r in rels:
            assert r.tenant_id == "t1"
            assert r.project_id == "p1"

    def test_relationship_requires_tenant_id(self, extractor):
        with pytest.raises(ValueError, match="tenant_id"):
            extractor.map_relationships([], "", tenant_id="")

    def test_relationship_has_source_and_target(self, extractor):
        text = "tool deployer function build"
        entities = extractor.extract_entities(text, "t1", "p1")
        rels = extractor.map_relationships(entities, text, "t1", "p1")
        for r in rels:
            assert r.source_id != r.target_id


# ── TestGraphTraversalIsolation (5) ──────────────────────────

class TestGraphTraversalIsolation:
    @pytest.fixture
    def graph(self):
        tmp = tempfile.mkdtemp(prefix="kg_")
        g = GraphStore(base_dir=tmp)
        e1 = Entity("e1", "t1", "p1", "deployer", EntityType.TOOL, "deployment tool")
        e2 = Entity("e2", "t1", "p1", "timeout_error", EntityType.ERROR, "timeout")
        e3 = Entity("e3", "t2", "p1", "deployer", EntityType.TOOL, "other tenant tool")
        g.add_node(e1)
        g.add_node(e2)
        g.add_node(e3)
        g.add_edge(Relationship("r1", "t1", "p1", "e1", "e2", EdgeType.FAILS_WITH))
        yield g
        g.close()

    def test_cross_tenant_isolation(self, graph):
        nodes_t1 = graph.find_nodes_by_type("t1", "p1", EntityType.TOOL.value)
        nodes_t2 = graph.find_nodes_by_type("t2", "p1", EntityType.TOOL.value)
        assert len(nodes_t1) == 1
        assert len(nodes_t2) == 1
        for n in nodes_t1:
            assert n["tenant_id"] == "t1"

    def test_neighbor_isolation(self, graph):
        neighbors = graph.get_neighbors("e1", "t1", "p1")
        for n in neighbors:
            assert n["tenant_id"] == "t1"

    def test_path_does_not_cross_tenants(self, graph):
        path = graph.query_path("e3", "e3", "t2")
        assert len(path) >= 1
        for n in path:
            assert n["tenant_id"] == "t2"

    def test_node_requires_tenant_id(self):
        with pytest.raises(ValueError, match="tenant_id"):
            Entity("bad", "", "p1", "x", EntityType.CONCEPT, "")

    def test_query_path_latency(self, graph):
        import time
        start = time.perf_counter()
        graph.query_path("e1", "e1", "t1")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.002, f"query_path latency {elapsed*1000:.2f}ms >= 2ms"
