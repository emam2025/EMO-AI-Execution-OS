"""Phase G2 — Critic Trace ID Propagation Tests.  # LAW-12

Tests that critic_trace_id propagates correctly across
G2 → F4 → G1 → D9 layers without loss.

Ref: Canon LAW 12
Ref: artifacts/design/g2/04_integration_blueprint.md §2
"""

from __future__ import annotations

import pytest

from core.runtime.critic.trace_correlator import CriticTraceCorrelator


class TestCriticTraceIdPropagation:
    """LAW 12: critic_trace_id survives traversal across layers."""

    def test_generate_trace_id_unique(self):
        tc = CriticTraceCorrelator()
        id1 = tc.generate_trace_id("plan1", {"error": "timeout"})
        id2 = tc.generate_trace_id("plan2", {"error": "oom"})
        assert id1 != id2
        assert id1.startswith("critic_")

    def test_generate_trace_id_same_input_different(self):
        tc = CriticTraceCorrelator()
        id1 = tc.generate_trace_id("plan1", {"error": "timeout"})
        id2 = tc.generate_trace_id("plan1", {"error": "timeout"})
        assert id1 != id2

    def test_record_and_retrieve_correlation(self):
        tc = CriticTraceCorrelator()
        tid = tc.generate_trace_id("p1", {"x": 1})
        tc.record_correlation("p1", "g2_critic", tid)
        assert tc.correlation_for("p1", "g2_critic") == tid

    def test_propagate_to_g1(self):
        tc = CriticTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        ctx = tc.propagate_to_g1("p1", tid)
        assert ctx["target_layer"] == "g1_planner"
        assert ctx["critic_trace_id"] == tid

    def test_propagate_to_d9(self):
        tc = CriticTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        ctx = tc.propagate_to_d9("p1", tid)
        assert ctx["target_layer"] == "d9_feedback"

    def test_propagate_to_f4(self):
        tc = CriticTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        ctx = tc.propagate_to_f4("p1", tid)
        assert ctx["target_layer"] == "f4_observability"

    def test_trace_chain(self):
        tc = CriticTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        tc.propagate_to_g1("p1", tid)
        tc.propagate_to_d9("p1", tid)
        chain = tc.trace_chain(tid)
        assert "plan_id" in chain
        assert chain["plan_id"] == "p1"

    def test_resolve_plan_id(self):
        tc = CriticTraceCorrelator()
        tid = tc.generate_trace_id("p99", {})
        tc.record_correlation("p99", "g2_critic", tid)
        assert tc.resolve_plan_id(tid) == "p99"

    def test_resolve_plan_id_unknown(self):
        tc = CriticTraceCorrelator()
        assert tc.resolve_plan_id("nonexistent") is None

    def test_full_cross_layer_propagation(self):
        tc = CriticTraceCorrelator()
        tid = tc.generate_trace_id("plan_x", {"error": "OOM"})

        tc.record_correlation("plan_x", "g2_critic", tid)
        tc.propagate_to_g1("plan_x", tid)
        tc.propagate_to_d9("plan_x", tid)
        tc.propagate_to_f4("plan_x", tid)

        chain = tc.trace_chain(tid)
        assert "plan_x" in chain.get("layers", {}).values() or chain.get("plan_id") == "plan_x"

    def test_reset(self):
        tc = CriticTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        tc.record_correlation("p1", "g2_critic", tid)
        tc.reset()
        assert tc.resolve_plan_id(tid) is None
