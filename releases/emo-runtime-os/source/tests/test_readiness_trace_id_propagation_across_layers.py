"""Phase J3 — Readiness Trace ID Propagation Tests.  # LAW-3 LAW-5 LAW-8 LAW-12 RULE-4

Tests that readiness_trace_id propagates correctly across all J3 layers:
ChaosInjector → LoadOrchestrator → StabilityValidator → CertificationGate.

Ref: artifacts/design/j3/04_integration_blueprint.md §2 (Correlation ID Strategy)
Ref: Canon LAW 5, LAW 8, LAW 12, RULE 4
"""

from __future__ import annotations

import asyncio

import pytest

from core.readiness.trace_correlator import ReadinessTraceCorrelator

TRACE_ID = "rdns_test_trace_propagation_001"


class TestReadinessTraceGeneration:
    """LAW 12: readiness_trace_id generation and format."""

    def test_generate_trace_id_format(self) -> None:
        correlator = ReadinessTraceCorrelator()
        trace_id = correlator.generate_readiness_trace_id("sess_1", "scenario_1")
        assert trace_id.startswith("rdns_")
        assert len(trace_id) > 10  # rdns_ + 28 hex chars = 33+

    def test_generate_unique_ids(self) -> None:
        correlator = ReadinessTraceCorrelator()
        t1 = correlator.generate_readiness_trace_id("sess_1", "scenario_1")
        t2 = correlator.generate_readiness_trace_id("sess_1", "scenario_1")
        assert t1 != t2  # Different timestamps

    def test_correlation_for_unknown(self) -> None:
        correlator = ReadinessTraceCorrelator()
        result = correlator.correlation_for("nonexistent", "chaos_injector")
        assert result == ""


class TestChaosToLoadTraceChain:
    """readiness_trace_id flows from ChaosInjector -> LoadOrchestrator."""

    def test_chaos_layer_recorded(self) -> None:
        correlator = ReadinessTraceCorrelator()
        result = correlator.propagate_to_chaos(TRACE_ID, "inj_001")
        assert result["readiness_trace_id"] == TRACE_ID
        assert result["injection_id"] == "inj_001"
        assert correlator.correlation_for(TRACE_ID, "chaos_injector") == "inj_001"

    def test_load_layer_recorded(self) -> None:
        correlator = ReadinessTraceCorrelator()
        correlator.propagate_to_chaos(TRACE_ID, "inj_001")
        result = correlator.propagate_to_load(TRACE_ID, "prof_001")
        assert result["profile_id"] == "prof_001"
        assert correlator.correlation_for(TRACE_ID, "load_orchestrator") == "prof_001"

    def test_stability_layer_recorded(self) -> None:
        correlator = ReadinessTraceCorrelator()
        correlator.propagate_to_chaos(TRACE_ID, "inj_001")
        correlator.propagate_to_load(TRACE_ID, "prof_001")
        result = correlator.propagate_to_stability(TRACE_ID, "m_001")
        assert result["metric_id"] == "m_001"
        assert correlator.correlation_for(TRACE_ID, "stability_validator") == "m_001"

    def test_certification_layer_recorded(self) -> None:
        correlator = ReadinessTraceCorrelator()
        correlator.propagate_to_chaos(TRACE_ID, "inj_001")
        correlator.propagate_to_load(TRACE_ID, "prof_001")
        correlator.propagate_to_stability(TRACE_ID, "m_001")
        result = correlator.propagate_to_certification(TRACE_ID, "rpt_001")
        assert result["report_id"] == "rpt_001"
        assert correlator.correlation_for(TRACE_ID, "certification_gate") == "rpt_001"


class TestF4ObservabilityPropagation:
    """readiness_trace_id propagates to F4 Observability."""

    def test_f4_layer_recorded(self) -> None:
        correlator = ReadinessTraceCorrelator()
        result = correlator.propagate_to_f4(TRACE_ID)
        assert result["target_layer"] == "f4_observability"
        assert result["f4_span_id"].startswith("f4_")
        assert correlator.correlation_for(TRACE_ID, "f4_observability") != ""

    def test_full_trace_chain(self) -> None:
        correlator = ReadinessTraceCorrelator()
        tid = correlator.generate_readiness_trace_id("sess_1", "scenario_1")
        correlator.propagate_to_chaos(tid, "inj_001")
        correlator.propagate_to_load(tid, "prof_001")
        correlator.propagate_to_certification(tid, "rpt_001")
        correlator.propagate_to_f4(tid)
        chain = correlator.trace_chain(tid)
        assert "layers" in chain
        assert "chaos_injector" in chain["layers"]
        assert "load_orchestrator" in chain["layers"]
        assert "certification_gate" in chain["layers"]
        assert "f4_observability" in chain["layers"]

    def test_trace_chain_returns_empty_for_unknown(self) -> None:
        correlator = ReadinessTraceCorrelator()
        chain = correlator.trace_chain("unknown")
        assert chain == {}

    def test_all_traces(self) -> None:
        correlator = ReadinessTraceCorrelator()
        t1 = correlator.generate_readiness_trace_id("s1", "sc1")
        t2 = correlator.generate_readiness_trace_id("s2", "sc2")
        correlator.propagate_to_chaos(t1, "inj_001")
        correlator.propagate_to_load(t2, "prof_001")
        traces = correlator.all_traces()
        assert t1 in traces
        assert t2 in traces

    def test_reset_clears_traces(self) -> None:
        correlator = ReadinessTraceCorrelator()
        tid = correlator.generate_readiness_trace_id("s1", "sc1")
        correlator.propagate_to_chaos(tid, "inj_001")
        assert len(correlator.all_traces()) > 0
        correlator.reset()
        assert len(correlator.all_traces()) == 0
