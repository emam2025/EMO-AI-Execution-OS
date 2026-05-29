"""Unit tests for orchestration_trace_id propagation."""

from __future__ import annotations

import pytest

from core.orchestration.trace_correlator import OrchestrationTraceCorrelator


class TestOrchestrationTraceIdPropagation:
    def test_generate_orchestration_trace_id(self) -> None:
        ctc = OrchestrationTraceCorrelator()
        tid = ctc.generate_orchestration_trace_id("summarize", "ten_a")
        assert tid.startswith("og_")
        assert len(tid) == 31  # "og_" + 28 hex

    def test_generate_different_intent_different_id(self) -> None:
        ctc = OrchestrationTraceCorrelator()
        t1 = ctc.generate_orchestration_trace_id("summarize", "ten_a")
        t2 = ctc.generate_orchestration_trace_id("translate", "ten_a")
        assert t1 != t2

    def test_record_event(self) -> None:
        ctc = OrchestrationTraceCorrelator()
        tid = ctc.generate_orchestration_trace_id("test", "ten_a")
        ctc.record_event(tid, "plan_proposed", "planner", "ten_a")
        chain = ctc.get_trace_chain(tid)
        assert chain["total_events"] == 1

    def test_verify_full_propagation(self) -> None:
        ctc = OrchestrationTraceCorrelator()
        tid = ctc.generate_orchestration_trace_id("test", "ten_a")
        ctc.record_event(tid, "plan_proposed", "planner", "ten_a")
        ctc.record_event(tid, "plan_approved", "critic", "ten_a")
        ctc.record_event(tid, "optimization_applied", "optimizer", "ten_a")
        v = ctc.verify_full_propagation(tid)
        assert v["fully_propagated"] is True
        assert v["event_count"] == 3

    def test_empty_trace_returns_no_events(self) -> None:
        ctc = OrchestrationTraceCorrelator()
        v = ctc.verify_full_propagation("nonexistent")
        assert v["fully_propagated"] is False
        assert v["event_count"] == 0

    def test_reset(self) -> None:
        ctc = OrchestrationTraceCorrelator()
        ctc.record_event(ctc.generate_orchestration_trace_id("a", "t"), "e", "p", "t")
        assert len(ctc.all_traces()) >= 1
        ctc.reset()
        assert len(ctc.all_traces()) == 0
