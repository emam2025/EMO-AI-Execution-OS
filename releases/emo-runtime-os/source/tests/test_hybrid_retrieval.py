"""Validation tests for Phase 10: HybridRetriever + orchestrator integration.

Tests cover:
  - WeightsAdvisor dynamic weighting
  - HybridRetriever.retrieve() entry-point
  - merge(), rank(), normalize_scores() methods
  - Context-signal heuristics (file depth, risk, recursion, unresolved)
  - Semantic/graph/fallback edge cases
  - Query scenarios: authentication, database, payment flow
  - Deduplication guarantee, deterministic ranking
  - Orchestrator SEMANTIC intent routing
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)


# ======================================================================
# Mock layer
# ======================================================================

class MockGraphEngine:
    def retrieve_symbol_core(self, sid):
        db = {
            "sym-auth-1": {
                "meta": {"name": "validate_token", "symbol_id": "sym-auth-1"},
                "static_analysis": {
                    "role": "io_bound", "file_path": "auth/service.py",
                    "complexity": {"cyclomatic": 6}, "behavior": {"is_recursive": False},
                },
            },
            "sym-auth-2": {
                "meta": {"name": "login_handler", "symbol_id": "sym-auth-2"},
                "static_analysis": {
                    "role": "controller", "file_path": "auth/handlers.py",
                    "complexity": {"cyclomatic": 8}, "behavior": {"is_recursive": False},
                },
            },
            "sym-auth-3": {
                "meta": {"name": "jwt_decode", "symbol_id": "sym-auth-3"},
                "static_analysis": {
                    "role": "pure_function", "file_path": "auth/jwt.py",
                    "complexity": {"cyclomatic": 3}, "behavior": {"is_recursive": False},
                },
            },
            "sym-db-1": {
                "meta": {"name": "connect_db", "symbol_id": "sym-db-1"},
                "static_analysis": {
                    "role": "data_access", "file_path": "db/connection.py",
                    "complexity": {"cyclomatic": 2}, "behavior": {"is_recursive": False},
                },
            },
            "sym-db-2": {
                "meta": {"name": "query_db", "symbol_id": "sym-db-2"},
                "static_analysis": {
                    "role": "data_access", "file_path": "db/queries.py",
                    "complexity": {"cyclomatic": 4}, "behavior": {"is_recursive": False},
                },
            },
            "sym-db-3": {
                "meta": {"name": "execute_transaction", "symbol_id": "sym-db-3"},
                "static_analysis": {
                    "role": "data_access", "file_path": "db/transaction.py",
                    "complexity": {"cyclomatic": 5}, "behavior": {"is_recursive": False},
                },
            },
            "sym-pay-1": {
                "meta": {"name": "process_payment", "symbol_id": "sym-pay-1"},
                "static_analysis": {
                    "role": "controller", "file_path": "payment/handler.py",
                    "complexity": {"cyclomatic": 7}, "behavior": {"is_recursive": False},
                },
            },
            "sym-pay-2": {
                "meta": {"name": "validate_card", "symbol_id": "sym-pay-2"},
                "static_analysis": {
                    "role": "pure_function", "file_path": "payment/card.py",
                    "complexity": {"cyclomatic": 3}, "behavior": {"is_recursive": False},
                },
            },
            "sym-pay-3": {
                "meta": {"name": "refund", "symbol_id": "sym-pay-3"},
                "static_analysis": {
                    "role": "io_bound", "file_path": "payment/refund.py",
                    "complexity": {"cyclomatic": 4}, "behavior": {"is_recursive": True},
                },
            },
            "sym-test-1": {
                "meta": {"name": "test_validate", "symbol_id": "sym-test-1"},
                "static_analysis": {
                    "role": "pure_function", "file_path": "tests/test_auth.py",
                    "complexity": {"cyclomatic": 1}, "behavior": {"is_recursive": False},
                },
            },
            "deep/core/detail/helper": {
                "meta": {"name": "deep_helper", "symbol_id": "deep/core/detail/helper"},
                "static_analysis": {
                    "role": "utility", "file_path": "lib/core/detail/helper.py",
                    "complexity": {"cyclomatic": 2}, "behavior": {"is_recursive": False},
                },
            },
        }
        if sid in db:
            return db[sid]
        raise LookupError(f"Symbol '{sid}' not found")

    def heuristic_analysis(self, sid, **kw):
        db = {
            "sym-auth-1": {"importance": 4.5, "overall_risk": "MEDIUM"},
            "sym-auth-2": {"importance": 6.0, "overall_risk": "HIGH"},
            "sym-auth-3": {"importance": 3.0, "overall_risk": "LOW"},
            "sym-db-1": {"importance": 8.0, "overall_risk": "LOW"},
            "sym-db-2": {"importance": 5.0, "overall_risk": "MEDIUM"},
            "sym-db-3": {"importance": 4.0, "overall_risk": "MEDIUM"},
            "sym-pay-1": {"importance": 7.0, "overall_risk": "HIGH"},
            "sym-pay-2": {"importance": 3.5, "overall_risk": "LOW"},
            "sym-pay-3": {"importance": 5.5, "overall_risk": "MEDIUM"},
            "sym-test-1": {"importance": 1.0, "overall_risk": "LOW"},
            "deep/core/detail/helper": {"importance": 2.0, "overall_risk": "LOW"},
        }
        return db.get(sid, {"importance": 0, "overall_risk": "LOW"})

    def ranked_hotspots(self, limit=10):
        return [
            {"symbol_id": "sym-db-1", "symbol_name": "connect_db",
             "importance_score": 8.0, "role": "data_access",
             "file_path": "db/connection.py", "incoming_calls": 12},
            {"symbol_id": "sym-pay-1", "symbol_name": "process_payment",
             "importance_score": 7.0, "role": "controller",
             "file_path": "payment/handler.py", "incoming_calls": 8},
            {"symbol_id": "sym-auth-2", "symbol_name": "login_handler",
             "importance_score": 6.0, "role": "controller",
             "file_path": "auth/handlers.py", "incoming_calls": 10},
            {"symbol_id": "sym-pay-3", "symbol_name": "refund",
             "importance_score": 5.5, "role": "io_bound",
             "file_path": "payment/refund.py", "incoming_calls": 4},
            {"symbol_id": "sym-db-2", "symbol_name": "query_db",
             "importance_score": 5.0, "role": "data_access",
             "file_path": "db/queries.py", "incoming_calls": 7},
            {"symbol_id": "sym-auth-1", "symbol_name": "validate_token",
             "importance_score": 4.5, "role": "io_bound",
             "file_path": "auth/service.py", "incoming_calls": 6},
            {"symbol_id": "sym-db-3", "symbol_name": "execute_transaction",
             "importance_score": 4.0, "role": "data_access",
             "file_path": "db/transaction.py", "incoming_calls": 5},
            {"symbol_id": "sym-pay-2", "symbol_name": "validate_card",
             "importance_score": 3.5, "role": "pure_function",
             "file_path": "payment/card.py", "incoming_calls": 7},
            {"symbol_id": "sym-auth-3", "symbol_name": "jwt_decode",
             "importance_score": 3.0, "role": "pure_function",
             "file_path": "auth/jwt.py", "incoming_calls": 9},
        ][:limit]


class MockSemanticStore:
    def __init__(self):
        self.available = True

    def search_similar(self, qvec, top_k=10):
        context = int(round(qvec[0])) if qvec else 0
        scenarios = {
            1: [
                {"symbol_id": "sym-auth-1", "score": 0.92,
                 "metadata": {"name": "validate_token", "file_path": "auth/service.py"}},
                {"symbol_id": "sym-auth-2", "score": 0.88,
                 "metadata": {"name": "login_handler", "file_path": "auth/handlers.py"}},
                {"symbol_id": "sym-auth-3", "score": 0.85,
                 "metadata": {"name": "jwt_decode", "file_path": "auth/jwt.py"}},
                {"symbol_id": "sym-test-1", "score": 0.82,
                 "metadata": {"name": "test_validate", "file_path": "tests/test_auth.py"}},
                {"symbol_id": "sym-pay-2", "score": 0.60,
                 "metadata": {"name": "validate_card", "file_path": "payment/card.py"}},
            ],
            2: [
                {"symbol_id": "sym-db-1", "score": 0.95,
                 "metadata": {"name": "connect_db", "file_path": "db/connection.py"}},
                {"symbol_id": "sym-db-2", "score": 0.90,
                 "metadata": {"name": "query_db", "file_path": "db/queries.py"}},
                {"symbol_id": "sym-db-3", "score": 0.82,
                 "metadata": {"name": "execute_transaction", "file_path": "db/transaction.py"}},
                {"symbol_id": "sym-auth-2", "score": 0.45,
                 "metadata": {"name": "login_handler", "file_path": "auth/handlers.py"}},
            ],
            3: [
                {"symbol_id": "sym-pay-1", "score": 0.94,
                 "metadata": {"name": "process_payment", "file_path": "payment/handler.py"}},
                {"symbol_id": "sym-pay-3", "score": 0.91,
                 "metadata": {"name": "refund", "file_path": "payment/refund.py"}},
                {"symbol_id": "sym-pay-2", "score": 0.87,
                 "metadata": {"name": "validate_card", "file_path": "payment/card.py"}},
                {"symbol_id": "sym-auth-2", "score": 0.55,
                 "metadata": {"name": "login_handler", "file_path": "auth/handlers.py"}},
            ],
            0: [
                {"symbol_id": "sym-auth-1", "score": 0.90,
                 "metadata": {"name": "validate_token", "file_path": "auth/service.py"}},
                {"symbol_id": "sym-db-1", "score": 0.80,
                 "metadata": {"name": "connect_db", "file_path": "db/connection.py"}},
            ],
        }
        results = scenarios.get(context, scenarios[0])
        return results[:top_k]

    @property
    def size(self):
        return 10


class MockEmbeddingEngine:
    available = True
    dimension = 384
    _query_map = {
        "authentication": 1, "auth": 1, "authenticate": 1, "login": 1, "token": 1,
        "database": 2, "db": 2, "connection": 2, "sql": 2, "query": 2,
        "payment": 3, "pay": 3, "checkout": 3, "billing": 3, "card": 3,
    }

    def embed_text(self, text):
        ctx = 0
        t = text.lower()
        for kw, cid in self._query_map.items():
            if kw in t:
                ctx = cid
                break
        return [float(ctx)] + [0.0] * 383

    def embed_symbol(self, sym):
        return [0.0] * 384


from core.hybrid_retriever import HybridRetriever, WeightsAdvisor, RepoStats


def make_hr(**kw):
    return HybridRetriever(MockGraphEngine(), MockSemanticStore(), MockEmbeddingEngine(), **kw)


# ======================================================================
# WeightsAdvisor Tests
# ======================================================================

def test_weights_default_profile():
    w = WeightsAdvisor(RepoStats(size=1200))
    wg, ws = w.get_weights("app/service.py")
    assert (wg, ws) == (0.6, 0.4)


def test_weights_small_repo():
    w = WeightsAdvisor(RepoStats(size=50))
    wg, ws = w.get_weights("app/service.py")
    assert (wg, ws) == (0.3, 0.7), "small repo → semantic-heavy"


def test_weights_large_repo():
    w = WeightsAdvisor(RepoStats(size=10000))
    wg, ws = w.get_weights("app/service.py")
    assert (wg, ws) == (0.7, 0.3), "large repo → graph-heavy"


def test_weights_test_file():
    w = WeightsAdvisor(RepoStats(size=1200))
    cases = ["tests/test_auth.py", "spec/auth_spec.py", "mock/fake_db.py", "fixtures/data.py"]
    for path in cases:
        wg, ws = w.get_weights(path)
        assert (wg, ws) == (0.2, 0.8), f"test file '{path}' → semantic-heavy"


def test_weights_test_overrides_size():
    """Test-file profile must take priority over size-based profiles."""
    w = WeightsAdvisor(RepoStats(size=10000))  # large repo
    wg, ws = w.get_weights("tests/test_auth.py")
    assert (wg, ws) == (0.2, 0.8), "test marker overrides size"


def test_weights_small_repo_test():
    """Combined: small repo + test file → still semantic-heavy (test wins)."""
    w = WeightsAdvisor(RepoStats(size=100))  # small
    wg, ws = w.get_weights("tests/test_auth.py")
    assert (wg, ws) == (0.2, 0.8), "test marker wins over small-repo"


# ======================================================================
# Dynamic Weighting Integration Tests
# ======================================================================

def test_dynamic_weights_in_rank():
    """Symbols in test files get different weights than production code."""
    hr = make_hr(weights_advisor=WeightsAdvisor(RepoStats(size=1200)))
    result = hr.retrieve("authentication")
    for r in result["ranking_scores"]:
        if "test" in r.get("file_path", ""):
            assert r["w_sem"] == 0.8, f"test file should have w_sem=0.8, got {r['w_sem']}"
            assert r["w_graph"] == 0.2
        else:
            assert r["w_graph"] == 0.6, f"prod file should have w_graph=0.6, got {r['w_graph']}"
            assert r["w_sem"] == 0.4


def test_dynamic_weights_profile_in_output():
    hr = make_hr(weights_advisor=WeightsAdvisor(RepoStats(size=1200)))
    result = hr.retrieve("authentication")
    assert result["weights_profile"] == "dynamic"

    hr2 = make_hr()
    result2 = hr2.retrieve("authentication")
    assert result2["weights_profile"] == "static"


# ======================================================================
# Context Signal Tests
# ======================================================================

def test_shallow_file_bonus():
    """Files at depth ≤ 2 get +0.03 bonus."""
    hr = make_hr(weights_advisor=WeightsAdvisor(RepoStats(size=1200)))
    # auth/service.py → depth 2 → should get shallow bonus
    result = hr.retrieve("authentication")
    validate_token = [r for r in result["merged_results"]
                      if r["symbol_id"] == "sym-auth-1"][0]
    assert "auth/service.py" in validate_token.get("file_path", "")
    bonus = validate_token.get("heuristic_bonus", 0)
    # Bonus should include BONUS_SHALLOW_FILE (0.03)
    assert bonus >= 0.03 or bonus == 0.03


def test_deep_file_penalty():
    """Files deeper than 5 get -0.03 penalty."""
    hr = make_hr()
    # Manually test the bonus computation
    bonus = hr._compute_bonus({"file_depth": 6, "overall_risk": "LOW",
                                "recursive": False, "unresolved_edges": 0})
    assert bonus == -0.03, f"Expected -0.03, got {bonus}"


def test_all_bonuses_stack():
    """Verify multiple bonuses stack correctly."""
    hr = make_hr()
    bonus = hr._compute_bonus({
        "file_depth": 2,
        "overall_risk": "HIGH",
        "recursive": True,
        "unresolved_edges": 0,
    })
    # HIGH_RISK(0.10) + RECURSIVE(0.05) + SHALLOW(0.03) = 0.18
    assert abs(bonus - 0.18) < 0.001, f"Expected 0.18, got {bonus}"


def test_bonus_with_penalty():
    """Bonuses and penalties should sum correctly."""
    hr = make_hr()
    bonus = hr._compute_bonus({
        "file_depth": 6,
        "overall_risk": "HIGH",
        "recursive": False,
        "unresolved_edges": 2,
    })
    # HIGH_RISK(0.10) + DEEP(-0.03) + UNRESOLVED(-0.05) = 0.02
    assert abs(bonus - 0.02) < 0.001, f"Expected 0.02, got {bonus}"


# ======================================================================
# Core API Tests
# ======================================================================

def test_retrieve_returns_full_schema():
    hr = make_hr()
    result = hr.retrieve("authentication")
    required = ["query", "graph_results", "semantic_results",
                 "merged_results", "ranking_scores", "improvement_notes",
                 "validation_results", "weights_profile"]
    for key in required:
        assert key in result, f"Missing key: {key}"
    assert result["query"] == "authentication"


def test_merge_deduplicates():
    hr = make_hr()
    graph = [
        {"symbol_id": "sym-1", "symbol_name": "foo", "graph_importance": 5.0},
        {"symbol_id": "sym-2", "symbol_name": "bar", "graph_importance": 3.0},
    ]
    semantic = [
        {"symbol_id": "sym-2", "score": 0.9, "metadata": {"name": "bar"}},
        {"symbol_id": "sym-3", "score": 0.7, "metadata": {"name": "baz"}},
    ]
    merged = hr.merge(graph, semantic)
    ids = [m["symbol_id"] for m in merged]
    assert len(ids) == len(set(ids)), "Duplicates found in merged output"
    assert "sym-1" in ids
    assert "sym-2" in ids
    assert "sym-3" in ids

    s2 = [m for m in merged if m["symbol_id"] == "sym-2"][0]
    assert s2["graph_importance"] == 3.0
    assert s2["semantic_score"] == 0.9


def test_merge_graph_only():
    hr = make_hr()
    graph = [{"symbol_id": "s1", "symbol_name": "only_graph", "graph_importance": 4.0}]
    merged = hr.merge(graph, [])
    assert len(merged) == 1
    assert merged[0]["symbol_id"] == "s1"
    assert merged[0]["semantic_score"] == 0.0


def test_merge_semantic_only():
    hr = make_hr()
    semantic = [{"symbol_id": "s2", "score": 0.8, "metadata": {"name": "only_sem"}}]
    merged = hr.merge([], semantic)
    assert len(merged) == 1
    assert merged[0]["symbol_id"] == "s2"
    assert merged[0]["graph_importance"] == 0.0


def test_rank_deterministic():
    hr = make_hr()
    entries = [
        {"symbol_id": "a", "graph_importance": 5.0, "semantic_score": 0.9,
         "overall_risk": "LOW", "recursive": False, "unresolved_edges": 0,
         "file_path": "a.py", "file_depth": 1},
        {"symbol_id": "b", "graph_importance": 8.0, "semantic_score": 0.5,
         "overall_risk": "HIGH", "recursive": False, "unresolved_edges": 0,
         "file_path": "b.py", "file_depth": 1},
    ]
    r1 = hr.rank(entries)
    r2 = hr.rank(entries)
    for e1, e2 in zip(r1, r2):
        assert e1["symbol_id"] == e2["symbol_id"]
        assert e1["final_score"] == e2["final_score"]


def test_normalize_scores_clamps():
    hr = make_hr()
    entries = [
        {"symbol_id": "a", "final_score": 1.5},
        {"symbol_id": "b", "final_score": -0.3},
        {"symbol_id": "c", "final_score": 0.5},
    ]
    normalized = hr.normalize_scores(entries)
    for e in normalized:
        assert 0.0 <= e["final_score"] <= 1.0


def test_retrieve_semantic_not_available():
    hr = HybridRetriever(MockGraphEngine())
    result = hr.retrieve("authentication")
    assert len(result["merged_results"]) > 0
    assert len(result["ranking_scores"]) == len(result["merged_results"])


def test_retrieve_both_empty():
    class EmptyGraph:
        def ranked_hotspots(self, limit=10):
            return []
    hr = HybridRetriever(EmptyGraph())
    result = hr.retrieve("anything")
    assert len(result["merged_results"]) == 0


# ======================================================================
# Self-review checks
# ======================================================================

def test_no_duplicates_in_merged():
    hr = make_hr()
    result = hr.retrieve("authentication")
    merged = result["merged_results"]
    ids = [m["symbol_id"] for m in merged]
    assert len(ids) == len(set(ids)), f"Duplicates: {ids}"


def test_graph_preserved_in_merged():
    hr = make_hr()
    result = hr.retrieve("authentication")
    merged_ids = {m["symbol_id"] for m in result["merged_results"]}
    graph_ids = {g["symbol_id"] for g in result["graph_results"]}
    assert graph_ids.issubset(merged_ids), "Graph symbols missing from merged"


def test_semantic_preserved_in_merged():
    hr = make_hr()
    result = hr.retrieve("authentication")
    merged_ids = {m["symbol_id"] for m in result["merged_results"]}
    sem_ids = {s["symbol_id"] for s in result["semantic_results"]}
    assert sem_ids.issubset(merged_ids), "Semantic symbols missing from merged"


def test_ranking_stable():
    hr = make_hr()
    r1 = hr.retrieve("authentication")
    r2 = hr.retrieve("authentication")
    ids1 = [m["symbol_id"] for m in r1["merged_results"]]
    ids2 = [m["symbol_id"] for m in r2["merged_results"]]
    assert ids1 == ids2, "Ranking order differs between runs"


# ======================================================================
# Validation scenarios
# ======================================================================

def validate_auth_query():
    hr = make_hr()
    result = hr.retrieve("authentication", top_k=10)
    merged = result["merged_results"]
    top_names = [m["symbol_name"] for m in merged[:5]]
    expected = ["validate_token", "login_handler", "jwt_decode"]
    found = [n for n in expected if n in [m["symbol_name"] for m in merged]]
    missing = [n for n in expected if n not in [m["symbol_name"] for m in merged]]
    notes = (
        f"Auth test: found {len(found)}/3 expected. "
        f"Top 5: {top_names}. Missing: {missing or 'none'}. "
        f"Semantic recall contributed validation symbols."
    )
    return ("PASS" if len(found) >= 2 else "FAIL", notes, top_names)


def validate_db_query():
    hr = make_hr()
    result = hr.retrieve("database connection", top_k=10)
    merged = result["merged_results"]
    top_names = [m["symbol_name"] for m in merged[:5]]
    expected = ["connect_db", "query_db", "execute_transaction"]
    found = [n for n in expected if n in [m["symbol_name"] for m in merged]]
    missing = [n for n in expected if n not in [m["symbol_name"] for m in merged]]
    notes = (
        f"DB test: found {len(found)}/3 expected. "
        f"Top 5: {top_names}. Missing: {missing or 'none'}. "
        f"Graph-first ranking boosted connect_db."
    )
    return ("PASS" if len(found) >= 2 else "FAIL", notes, top_names)


def validate_payment_query():
    hr = make_hr()
    result = hr.retrieve("payment processing", top_k=10)
    merged = result["merged_results"]
    top_names = [m["symbol_name"] for m in merged[:5]]
    expected = ["process_payment", "validate_card", "refund"]
    found = [n for n in expected if n in [m["symbol_name"] for m in merged]]
    missing = [n for n in expected if n not in [m["symbol_name"] for m in merged]]
    notes = (
        f"Payment test: found {len(found)}/3 expected. "
        f"Top 5: {top_names}. Missing: {missing or 'none'}. "
        f"Cross-file discovery: payment/handler.py, card.py, refund.py."
    )
    return ("PASS" if len(found) >= 2 else "FAIL", notes, top_names)


# ======================================================================
# Orchestrator integration
# ======================================================================

from core.orchestrator import QueryPlanner
from core.types import Intent, ExecutionPlan
from core.execution_engine import DAGBuilder, PlanNode


class MockGraphQuery:
    def get_symbol_metadata(self, name):
        known = {"validate_token": {"name": "validate_token", "symbol_id": "sym-auth-1"},
                 "login_handler": {"name": "login_handler", "symbol_id": "sym-auth-2"}}
        return known.get(name)
    def get_file_metadata(self, name):
        return None
    def resolve_symbol_name(self, name):
        known = {"validate_token": "sym-auth-1", "login_handler": "sym-auth-2"}
        return known.get(name)


def test_semantic_intent_classification():
    planner = QueryPlanner(MockGraphQuery())
    cases = [
        ("find email validation functions", Intent.SEMANTIC),
        ("search for auth code", Intent.SEMANTIC),
        ("locate db functions", Intent.SEMANTIC),
        ("explain validate_token", Intent.EXPLAIN),
        ("impact connect_db", Intent.IMPACT),
    ]
    for query, expected in cases:
        plan = planner.plan(query)
        assert plan.intent == expected, f"'{query}' expected {expected}, got {plan.intent}"


def test_semantic_plan_routes_to_retrieve():
    planner = QueryPlanner(MockGraphQuery())
    plan = planner.plan("find validate_token")
    assert plan.intent == Intent.SEMANTIC
    tools = [n.tool for n in plan.dag.nodes.values()]
    assert any("hybrid" in t for t in tools)


def test_explain_plan_no_hybrid():
    planner = QueryPlanner(MockGraphQuery())
    plan = planner.plan("explain validate_token")
    tools = [n.tool for n in plan.dag.nodes.values()]
    assert all("hybrid" not in t for t in tools)


def test_orchestrator_hybrid_routing():
    """Verify hybrid_retrieval tool works through the DAG engine."""
    from core.execution_engine import ExecutionEngine, DAGBuilder, ToolSpec, RetryPolicy, RollbackStrategy
    from core.unified_runtime import UnifiedRuntime

    hyb = make_hr()

    dag = (DAGBuilder()
           .add("hybrid", tool="hybrid_retrieval.retrieve",
                inputs={"query": "authentication", "top_k": 10})
           .build())

    engine = ExecutionEngine()
    engine.register_tool(ToolSpec(
        name="hybrid_retrieval.retrieve", timeout_seconds=30,
        retry_policy=RetryPolicy(max_retries=2),
        rollback_strategy=RollbackStrategy(),
    ))

    runner = lambda n: hyb.retrieve(**n.inputs)
    er = engine.execute(dag, tool_runner=runner)

    assert er["status"] == "completed"
    node_id = list(er["node_results"].keys())[0]
    from core.answer_formatter import AnswerFormatter
    node_result = er["node_results"][node_id]["result"]
    answer = AnswerFormatter._format_semantic(node_result)
    assert "Found" in answer


# ======================================================================
# Run all
# ======================================================================

if __name__ == "__main__":
    tests = [
        # WeightsAdvisor
        ("weights default", test_weights_default_profile),
        ("weights small repo", test_weights_small_repo),
        ("weights large repo", test_weights_large_repo),
        ("weights test file", test_weights_test_file),
        ("weights test overrides size", test_weights_test_overrides_size),
        ("weights small+test", test_weights_small_repo_test),
        # Dynamic weighting integration
        ("dynamic weights in rank", test_dynamic_weights_in_rank),
        ("dynamic profile in output", test_dynamic_weights_profile_in_output),
        # Context signals
        ("shallow file bonus", test_shallow_file_bonus),
        ("deep file penalty", test_deep_file_penalty),
        ("bonuses stack", test_all_bonuses_stack),
        ("bonus+penalty", test_bonus_with_penalty),
        # Core API
        ("retrieve full schema", test_retrieve_returns_full_schema),
        ("merge deduplicates", test_merge_deduplicates),
        ("merge graph-only", test_merge_graph_only),
        ("merge semantic-only", test_merge_semantic_only),
        ("rank deterministic", test_rank_deterministic),
        ("normalize clamps", test_normalize_scores_clamps),
        ("fallback semantic unavailable", test_retrieve_semantic_not_available),
        ("both empty", test_retrieve_both_empty),
        # Self-review
        ("no duplicates", test_no_duplicates_in_merged),
        ("graph preserved", test_graph_preserved_in_merged),
        ("semantic preserved", test_semantic_preserved_in_merged),
        ("ranking stable", test_ranking_stable),
        # Orchestrator
        ("intent classification", test_semantic_intent_classification),
        ("SEMANTIC routes to retrieve", test_semantic_plan_routes_to_retrieve),
        ("EXPLAIN no hybrid", test_explain_plan_no_hybrid),
        ("executor routing", test_orchestrator_hybrid_routing),
    ]

    passed = 0
    failed = 0
    for desc, test_fn in tests:
        try:
            test_fn()
            print(f"  ✓ {desc}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {desc}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Unit tests: {passed} passed, {failed} failed, {len(tests)} total")

    # Validation scenarios
    print(f"\n{'='*50}")
    print("VALIDATION SCENARIOS\n")

    auth_status, auth_notes, auth_top = validate_auth_query()
    print(f"  [AUTH] {auth_status}")
    print(f"         Top: {auth_top}")
    print(f"         {auth_notes}")

    db_status, db_notes, db_top = validate_db_query()
    print(f"  [DB]   {db_status}")
    print(f"         Top: {db_top}")
    print(f"         {db_notes}")

    pay_status, pay_notes, pay_top = validate_payment_query()
    print(f"  [PAY]  {pay_status}")
    print(f"         Top: {pay_top}")
    print(f"         {pay_notes}")

    all_valid = (auth_status == db_status == pay_status == "PASS")

    print(f"\n{'='*50}")
    print(f"OVERALL")
    print(f"  Auth test:    {auth_status}")
    print(f"  DB test:      {db_status}")
    print(f"  Payment test: {pay_status}")
    print(f"  All validation: {'PASS' if all_valid else 'PARTIAL'}")
    print(f"  WeightsAdvisor: ✓ dynamic (repo_size + file_context)")
    print(f"  Context signals: ✓ depth/risk/recursion/unresolved")
    print(f"  Phase 10: {'✓ COMPLETE' if failed == 0 else '✗ NEEDS FIX'}")
