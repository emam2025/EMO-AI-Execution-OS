"""Phase G5 — Swarm Trace ID Propagation Across Layers.  # LAW-12

Tests mission_trace_id generation, recording, and propagation across
G1 → G5 → G2/G3 → F2 layers. Every swarm mission is back-traceable.

Ref: Canon LAW 12 (Traceability)
Ref: artifacts/design/g5/04_integration_blueprint.md §3
"""

from __future__ import annotations

import pytest

from core.runtime.multi_agent.swarm_trace_correlator import SwarmTraceCorrelator


def _make_correlator() -> SwarmTraceCorrelator:
    return SwarmTraceCorrelator()


class TestTraceIdGeneration:
    """mission_trace_id format and uniqueness."""

    def test_generate_trace_id_format(self):
        corr = _make_correlator()
        tid = corr.generate_trace_id("intent_001", "plan_001")
        assert tid.startswith("msn_")
        assert len(tid) >= 28

    def test_generate_trace_id_different_intents(self):
        corr = _make_correlator()
        t1 = corr.generate_trace_id("intent_a", "plan_001")
        t2 = corr.generate_trace_id("intent_b", "plan_001")
        assert t1 != t2

    def test_generate_trace_id_different_plans(self):
        corr = _make_correlator()
        t1 = corr.generate_trace_id("intent_001", "plan_a")
        t2 = corr.generate_trace_id("intent_001", "plan_b")
        assert t1 != t2


class TestTraceCorrelation:
    """Recording and retrieving trace correlations."""

    def test_record_and_correlation_for(self):
        corr = _make_correlator()
        corr.record_correlation("plan_001", "g5_swarm", "msn_test_id")
        tid = corr.correlation_for("plan_001", "g5_swarm")
        assert tid == "msn_test_id"

    def test_correlation_for_unknown_plan(self):
        corr = _make_correlator()
        tid = corr.correlation_for("unknown", "g5_swarm")
        assert tid == ""

    def test_correlation_for_unknown_layer(self):
        corr = _make_correlator()
        corr.record_correlation("plan_001", "g5_swarm", "msn_test")
        tid = corr.correlation_for("plan_001", "nonexistent_layer")
        assert tid == ""

    def test_record_correlation_multiple_layers(self):
        corr = _make_correlator()
        corr.record_correlation("plan_001", "g5_swarm", "msn_a")
        corr.record_correlation("plan_001", "g2_critic", "msn_a")
        assert corr.correlation_for("plan_001", "g5_swarm") == "msn_a"
        assert corr.correlation_for("plan_001", "g2_critic") == "msn_a"


class TestPropagationToLayers:
    """Propagation to each downstream layer."""

    def test_propagate_to_g1_returns_target_layer(self):
        corr = _make_correlator()
        ctx = corr.propagate_to_g1("plan_001", "msn_test")
        assert ctx["target_layer"] == "g1_planner"
        assert ctx["mission_trace_id"] == "msn_test"

    def test_propagate_to_g2_returns_target_layer(self):
        corr = _make_correlator()
        ctx = corr.propagate_to_g2("plan_001", "msn_test")
        assert ctx["target_layer"] == "g2_critic"

    def test_propagate_to_g3_returns_target_layer(self):
        corr = _make_correlator()
        ctx = corr.propagate_to_g3("plan_001", "msn_test")
        assert ctx["target_layer"] == "g3_optimizer"

    def test_propagate_to_f2_returns_target_layer(self):
        corr = _make_correlator()
        ctx = corr.propagate_to_f2("plan_001", "msn_test")
        assert ctx["target_layer"] == "f2_control"

    def test_propagate_records_correlation(self):
        corr = _make_correlator()
        corr.propagate_to_g1("plan_001", "msn_prop")
        tid = corr.correlation_for("plan_001", "g1_planner")
        assert tid == "msn_prop"

    def test_all_propagations_distinct(self):
        corr = _make_correlator()
        corr.propagate_to_g1("plan_001", "msn_x")
        corr.propagate_to_g2("plan_001", "msn_x")
        corr.propagate_to_g3("plan_001", "msn_x")
        corr.propagate_to_f2("plan_001", "msn_x")
        assert corr.correlation_for("plan_001", "g1_planner") == "msn_x"
        assert corr.correlation_for("plan_001", "g2_critic") == "msn_x"
        assert corr.correlation_for("plan_001", "g3_optimizer") == "msn_x"
        assert corr.correlation_for("plan_001", "f2_control") == "msn_x"


class TestTraceChain:
    """Full trace chain resolution."""

    def test_trace_chain_finds_mission(self):
        corr = _make_correlator()
        corr.propagate_to_g1("plan_a", "msn_chain")
        corr.propagate_to_g2("plan_a", "msn_chain")
        chain = corr.trace_chain("msn_chain")
        assert chain["plan_id"] == "plan_a"
        assert chain["mission_trace_id"] == "msn_chain"
        assert "g1_planner" in chain["layers"]
        assert "g2_critic" in chain["layers"]

    def test_trace_chain_returns_empty_for_unknown(self):
        corr = _make_correlator()
        chain = corr.trace_chain("nonexistent")
        assert chain == {}

    def test_resolve_plan_id_finds_correct_plan(self):
        corr = _make_correlator()
        corr.propagate_to_g1("plan_b", "msn_resolve")
        pid = corr.resolve_plan_id("msn_resolve")
        assert pid == "plan_b"

    def test_resolve_plan_id_returns_none_for_unknown(self):
        corr = _make_correlator()
        pid = corr.resolve_plan_id("unknown")
        assert pid is None


class TestReset:
    """Clear all state."""

    def test_reset_clears_all_correlations(self):
        corr = _make_correlator()
        corr.propagate_to_g1("plan_001", "msn_reset")
        corr.reset()
        assert corr.correlation_for("plan_001", "g1_planner") == ""
        assert corr.trace_chain("msn_reset") == {}
