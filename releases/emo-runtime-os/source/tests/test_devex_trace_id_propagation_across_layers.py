"""Phase J1 — DevEx Trace ID Propagation Tests.  # LAW-5 LAW-12

Tests devex_trace_id generation, uniqueness, propagation across all DevEx
layers (SDK, CLI, Doc, Spec), and chain reconstruction.

Ref: artifacts/design/j1/04_integration_blueprint.md §3 (Correlation ID Strategy)
Ref: Canon LAW 5, LAW 12
"""

from __future__ import annotations

import pytest

from core.devex.trace_correlator import DevExTraceCorrelator


class TestTraceIdGeneration:
    """Test devex_trace_id generation and format."""

    def test_generates_valid_devex_trace_id(self) -> None:
        corr = DevExTraceCorrelator()
        tid = corr.generate_devex_trace_id("sess_001", "sdk_submit")
        assert tid.startswith("dx_")
        assert len(tid) > 10

    def test_generates_unique_ids(self) -> None:
        corr = DevExTraceCorrelator()
        ids = {corr.generate_devex_trace_id("sess_001", "sdk_submit") for _ in range(50)}
        assert len(ids) == 50

    def test_trace_id_differs_by_operation_type(self) -> None:
        corr = DevExTraceCorrelator()
        t1 = corr.generate_devex_trace_id("sess_001", "sdk_submit")
        t2 = corr.generate_devex_trace_id("sess_001", "cli_status")
        assert t1 != t2


class TestTracePropagation:
    """Test devex_trace_id propagation across layers."""

    def test_propagate_to_f1(self) -> None:
        corr = DevExTraceCorrelator()
        result = corr.propagate_to_f1("dx_test", "f1_trace_001")
        assert result["target_layer"] == "f1_unified_api"
        assert corr.correlation_for("dx_test", "f1_unified_api") == "f1_trace_001"

    def test_propagate_to_f4(self) -> None:
        corr = DevExTraceCorrelator()
        result = corr.propagate_to_f4("dx_test")
        assert result["target_layer"] == "f4_observability"
        assert result["f4_span_id"].startswith("f4_")

    def test_propagate_to_sdk(self) -> None:
        corr = DevExTraceCorrelator()
        result = corr.propagate_to_sdk("dx_test", "sdk_001")
        assert result["target_layer"] == "sdk"

    def test_propagate_to_cli(self) -> None:
        corr = DevExTraceCorrelator()
        result = corr.propagate_to_cli("dx_test", "cli_001")
        assert result["target_layer"] == "cli"

    def test_propagate_to_doc(self) -> None:
        corr = DevExTraceCorrelator()
        result = corr.propagate_to_doc("dx_test", "doc_001")
        assert result["target_layer"] == "doc_generator"

    def test_propagate_to_spec(self) -> None:
        corr = DevExTraceCorrelator()
        result = corr.propagate_to_spec("dx_test", "spec_001")
        assert result["target_layer"] == "spec_publisher"


class TestEndToEndPropagation:
    """Test full devex_trace_id chain through all layers."""

    def test_full_chain_sdk_to_f4(self) -> None:
        corr = DevExTraceCorrelator()
        tid = corr.generate_devex_trace_id("sess_001", "sdk_submit")
        corr.propagate_to_sdk(tid, "sdk_op_001")
        corr.propagate_to_f1(tid, "f1_trace_001")
        corr.propagate_to_f4(tid)
        chain = corr.trace_chain(tid)
        assert "sdk" in chain["layers"]
        assert "f1_unified_api" in chain["layers"]
        assert "f4_observability" in chain["layers"]

    def test_full_chain_cli_to_spec(self) -> None:
        corr = DevExTraceCorrelator()
        tid = corr.generate_devex_trace_id("cli_sess", "cli_replay")
        corr.propagate_to_cli(tid, "cli_cmd_001")
        corr.propagate_to_f1(tid, "f1_replay_001")
        corr.propagate_to_spec(tid, "spec_001")
        chain = corr.trace_chain(tid)
        assert "cli" in chain["layers"]
        assert "spec_publisher" in chain["layers"]

    def test_all_traces_recorded(self) -> None:
        corr = DevExTraceCorrelator()
        t1 = corr.generate_devex_trace_id("sess_001", "op_a")
        t2 = corr.generate_devex_trace_id("sess_002", "op_b")
        corr.record_trace(t1, "test", "val1")
        corr.record_trace(t2, "test", "val2")
        assert len(corr.all_traces()) == 2

    def test_reset_clears_traces(self) -> None:
        corr = DevExTraceCorrelator()
        tid = corr.generate_devex_trace_id("sess_001", "op")
        corr.record_trace(tid, "test", "val")
        corr.reset()
        assert corr.all_traces() == []
