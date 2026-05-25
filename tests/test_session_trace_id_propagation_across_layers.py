"""Phase H1 — Session Trace ID Propagation Across Layers.  # LAW-12

Tests session_trace_id generation, recording, and propagation across
G5 → H1 → Phase 4 → F4 layers. Every session must be back-traceable.

Ref: Canon LAW 12 (Traceability)
Ref: artifacts/design/h1/04_integration_blueprint.md §3
"""

from __future__ import annotations

import pytest

from core.runtime.computer_use.trace_correlator import ComputerUseTraceCorrelator


@pytest.fixture
def correlator() -> ComputerUseTraceCorrelator:
    return ComputerUseTraceCorrelator()


class TestSessionTraceIdGeneration:
    """session_trace_id format and uniqueness."""

    def test_generate_format(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.generate_session_trace_id("msn_test", 0)
        assert tid.startswith("h1_")
        assert len(tid) >= 30

    def test_generate_different_mission_ids(self, correlator: ComputerUseTraceCorrelator):
        t1 = correlator.generate_session_trace_id("msn_a", 0)
        t2 = correlator.generate_session_trace_id("msn_b", 0)
        assert t1 != t2

    def test_generate_different_session_indices(self, correlator: ComputerUseTraceCorrelator):
        t1 = correlator.generate_session_trace_id("msn_test", 0)
        t2 = correlator.generate_session_trace_id("msn_test", 1)
        assert t1 != t2


class TestTraceCorrelation:
    """Recording and retrieving trace correlations."""

    def test_record_and_retrieve(self, correlator: ComputerUseTraceCorrelator):
        correlator.record_correlation("session_1", "h1_browser", "h1_test_id")
        tid = correlator.correlation_for("session_1", "h1_browser")
        assert tid == "h1_test_id"

    def test_unknown_layer_returns_empty(self, correlator: ComputerUseTraceCorrelator):
        correlator.record_correlation("session_1", "h1_browser", "h1_test")
        tid = correlator.correlation_for("session_1", "nonexistent")
        assert tid == ""

    def test_unknown_session_returns_empty(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.correlation_for("unknown", "h1_browser")
        assert tid == ""

    def test_multiple_layers_same_session(self, correlator: ComputerUseTraceCorrelator):
        correlator.record_correlation("session_2", "g5_swarm", "h1_id")
        correlator.record_correlation("session_2", "phase4_sandbox", "h1_id")
        assert correlator.correlation_for("session_2", "g5_swarm") == "h1_id"
        assert correlator.correlation_for("session_2", "phase4_sandbox") == "h1_id"


class TestPropagationToLayers:
    """Propagation to each downstream layer."""

    def test_propagate_to_g5(self, correlator: ComputerUseTraceCorrelator):
        ctx = correlator.propagate_to_g5("s_1", "h1_prop")
        assert ctx["target_layer"] == "g5_swarm"
        assert correlator.correlation_for("s_1", "g5_swarm") == "h1_prop"

    def test_propagate_to_phase4(self, correlator: ComputerUseTraceCorrelator):
        ctx = correlator.propagate_to_phase4("s_1", "h1_prop")
        assert ctx["target_layer"] == "phase4_sandbox"
        assert correlator.correlation_for("s_1", "phase4_sandbox") == "h1_prop"

    def test_propagate_to_f4(self, correlator: ComputerUseTraceCorrelator):
        ctx = correlator.propagate_to_f4("s_1", "h1_prop")
        assert ctx["target_layer"] == "f4_observability"
        assert correlator.correlation_for("s_1", "f4_observability") == "h1_prop"

    def test_all_three_propagations(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.generate_session_trace_id("msn_all", 0)
        correlator.propagate_to_g5("s_all", tid)
        correlator.propagate_to_phase4("s_all", tid)
        correlator.propagate_to_f4("s_all", tid)
        assert correlator.correlation_for("s_all", "g5_swarm") == tid
        assert correlator.correlation_for("s_all", "phase4_sandbox") == tid
        assert correlator.correlation_for("s_all", "f4_observability") == tid


class TestTraceChain:
    """Full trace chain resolution."""

    def test_trace_chain_finds_mission(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.generate_session_trace_id("msn_chain", 0)
        correlator.propagate_to_g5("s_chain", tid)
        correlator.propagate_to_phase4("s_chain", tid)
        chain = correlator.trace_chain(tid)
        assert chain["session_id"] == "s_chain"
        assert "g5_swarm" in chain["layers"]
        assert "phase4_sandbox" in chain["layers"]

    def test_trace_chain_returns_empty_for_unknown(self, correlator: ComputerUseTraceCorrelator):
        chain = correlator.trace_chain("nonexistent")
        assert chain == {}

    def test_resolve_session_id(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.generate_session_trace_id("msn_resolve", 0)
        correlator.propagate_to_phase4("s_resolve", tid)
        sid = correlator.resolve_session_id(tid)
        assert sid == "s_resolve"

    def test_resolve_unknown_returns_none(self, correlator: ComputerUseTraceCorrelator):
        pid = correlator.resolve_session_id("unknown")
        assert pid is None


class TestReset:
    """Clear all state."""

    def test_reset_clears_all(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.generate_session_trace_id("msn_reset", 0)
        correlator.propagate_to_g5("s_reset", tid)
        correlator.reset()
        assert correlator.correlation_for("s_reset", "g5_swarm") == ""
        assert correlator.trace_chain(tid) == {}
