"""Phase G3 — Optimizer Trace ID Propagation Tests.  # LAW-12

Tests that optimizer_trace_id propagates correctly across
G3 → G1 → F3 → G2 layers without loss.

Ref: Canon LAW 12
Ref: artifacts/design/g3/04_integration_blueprint.md §2
"""

from __future__ import annotations

import pytest

from core.runtime.optimizer.trace_correlator import OptimizerTraceCorrelator


class TestOptimizerTraceIdPropagation:
    """LAW 12: optimizer_trace_id survives traversal across layers."""

    def test_generate_trace_id_unique(self):
        tc = OptimizerTraceCorrelator()
        id1 = tc.generate_trace_id("plan1", {"cpu": 10})
        id2 = tc.generate_trace_id("plan2", {"cpu": 20})
        assert id1 != id2
        assert id1.startswith("opt_")

    def test_generate_trace_id_different_times(self):
        tc = OptimizerTraceCorrelator()
        id1 = tc.generate_trace_id("plan1", {"cpu": 10})
        id2 = tc.generate_trace_id("plan1", {"cpu": 10})
        assert id1 != id2

    def test_record_and_retrieve_correlation(self):
        tc = OptimizerTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        tc.record_correlation("p1", "g3_optimizer", tid)
        assert tc.correlation_for("p1", "g3_optimizer") == tid

    def test_propagate_to_g1(self):
        tc = OptimizerTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        ctx = tc.propagate_to_g1("p1", tid)
        assert ctx["target_layer"] == "g1_planner"
        assert ctx["optimizer_trace_id"] == tid

    def test_propagate_to_f3(self):
        tc = OptimizerTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        ctx = tc.propagate_to_f3("p1", tid)
        assert ctx["target_layer"] == "f3_scheduler"

    def test_propagate_to_g2(self):
        tc = OptimizerTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        ctx = tc.propagate_to_g2("p1", tid)
        assert ctx["target_layer"] == "g2_critic"

    def test_trace_chain(self):
        tc = OptimizerTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        tc.propagate_to_g1("p1", tid)
        tc.propagate_to_f3("p1", tid)
        chain = tc.trace_chain(tid)
        assert "plan_id" in chain
        assert chain["plan_id"] == "p1"

    def test_resolve_plan_id(self):
        tc = OptimizerTraceCorrelator()
        tid = tc.generate_trace_id("p99", {})
        tc.record_correlation("p99", "g3_optimizer", tid)
        assert tc.resolve_plan_id(tid) == "p99"

    def test_resolve_plan_id_unknown(self):
        tc = OptimizerTraceCorrelator()
        assert tc.resolve_plan_id("nonexistent") is None

    def test_full_cross_layer_propagation(self):
        tc = OptimizerTraceCorrelator()
        tid = tc.generate_trace_id("plan_x", {})
        tc.record_correlation("plan_x", "g3_optimizer", tid)
        tc.propagate_to_g1("plan_x", tid)
        tc.propagate_to_f3("plan_x", tid)
        tc.propagate_to_g2("plan_x", tid)
        chain = tc.trace_chain(tid)
        assert chain.get("plan_id") == "plan_x"

    def test_reset(self):
        tc = OptimizerTraceCorrelator()
        tid = tc.generate_trace_id("p1", {})
        tc.record_correlation("p1", "g3_optimizer", tid)
        tc.reset()
        assert tc.resolve_plan_id(tid) is None
