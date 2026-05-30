"""Phase G4 — Synthesis Trace ID Propagation Tests.  # LAW-12

Tests that synthesis_trace_id propagates correctly across
G1 → G4 → Phase4 Sandbox → ToolRegistry layers.

Ref: Canon LAW 12
Ref: artifacts/design/g4/04_integration_blueprint.md §3
"""

from __future__ import annotations

import pytest

from core.runtime.tool_synthesis.trace_correlator import SynthesisTraceCorrelator


class TestSynthesisTraceIdPropagation:
    """LAW 12: synthesis_trace_id survives traversal across layers."""

    def test_generate_trace_id_unique(self):
        tc = SynthesisTraceCorrelator()
        id1 = tc.generate_trace_id("intent1", "plan1")
        id2 = tc.generate_trace_id("intent2", "plan2")
        assert id1 != id2
        assert id1.startswith("syn_")

    def test_generate_trace_id_different_times(self):
        tc = SynthesisTraceCorrelator()
        id1 = tc.generate_trace_id("intent1", "plan1")
        id2 = tc.generate_trace_id("intent1", "plan1")
        assert id1 != id2

    def test_record_and_retrieve_correlation(self):
        tc = SynthesisTraceCorrelator()
        tid = tc.generate_trace_id("i1", "p1")
        tc.record_correlation("p1", "g4_synthesizer", tid)
        assert tc.correlation_for("p1", "g4_synthesizer") == tid

    def test_propagate_to_g1(self):
        tc = SynthesisTraceCorrelator()
        tid = tc.generate_trace_id("i1", "p1")
        ctx = tc.propagate_to_g1("p1", tid)
        assert ctx["target_layer"] == "g1_planner"
        assert ctx["synthesis_trace_id"] == tid

    def test_propagate_to_sandbox(self):
        tc = SynthesisTraceCorrelator()
        tid = tc.generate_trace_id("i1", "p1")
        ctx = tc.propagate_to_sandbox("p1", tid)
        assert ctx["target_layer"] == "phase4_sandbox"

    def test_propagate_to_registry(self):
        tc = SynthesisTraceCorrelator()
        tid = tc.generate_trace_id("i1", "p1")
        ctx = tc.propagate_to_registry("p1", tid)
        assert ctx["target_layer"] == "tool_registry"

    def test_trace_chain(self):
        tc = SynthesisTraceCorrelator()
        tid = tc.generate_trace_id("i1", "p1")
        tc.propagate_to_g1("p1", tid)
        tc.propagate_to_sandbox("p1", tid)
        tc.propagate_to_registry("p1", tid)
        chain = tc.trace_chain(tid)
        assert "plan_id" in chain
        assert chain["plan_id"] == "p1"
        assert len(chain["layers"]) == 3

    def test_full_cross_layer_propagation(self):
        tc = SynthesisTraceCorrelator()
        tid = tc.generate_trace_id("intent_x", "plan_x")
        tc.record_correlation("plan_x", "g4_synthesizer", tid)
        tc.propagate_to_g1("plan_x", tid)
        tc.propagate_to_sandbox("plan_x", tid)
        tc.propagate_to_registry("plan_x", tid)
        chain = tc.trace_chain(tid)
        assert chain.get("plan_id") == "plan_x"

    def test_resolve_plan_id(self):
        tc = SynthesisTraceCorrelator()
        tid = tc.generate_trace_id("i99", "p99")
        tc.record_correlation("p99", "g4_synthesizer", tid)
        assert tc.resolve_plan_id(tid) == "p99"

    def test_resolve_plan_id_unknown(self):
        tc = SynthesisTraceCorrelator()
        assert tc.resolve_plan_id("nonexistent") is None

    def test_reset(self):
        tc = SynthesisTraceCorrelator()
        tid = tc.generate_trace_id("i1", "p1")
        tc.record_correlation("p1", "g4_synthesizer", tid)
        tc.reset()
        assert tc.resolve_plan_id(tid) is None
