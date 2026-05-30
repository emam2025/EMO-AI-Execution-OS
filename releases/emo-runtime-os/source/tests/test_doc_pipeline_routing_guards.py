"""Phase J1 — Doc Pipeline Routing Guard Tests.  # LAW-1 LAW-2 LAW-5 LAW-8 LAW-12 LAW-13 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Tests all 7 pipeline stages (P1-P7), 5 doc guards (G-D1–G-D5), 5 CLI routing
guards (G-R1–G-R5), and the Deterministic Doc Guard (DDG) with SHA-256.

Ref: artifacts/design/j1/03_doc_and_cli_pipeline.md §1-4
"""

from __future__ import annotations

import hashlib

import pytest

from core.devex.doc_pipeline import DocPipeline, PipelineStage


TRACE_ID = "dx_test_pipeline_001"


class TestDocPipelineStages:
    """Test all 7 pipeline transitions (P1-P7)."""

    def test_p1_idle_to_scan_with_valid_snapshot(self) -> None:
        pipe = DocPipeline()
        result = pipe.run_pipeline(
            codegraph_snapshot={"modules": [{"name": "core"}], "version": "v1"},
            api_spec={"openapi": "3.1.0", "paths": {"/health": {}}, "components": {"schemas": {"Health": {}}}},
            canon_version="1.0",
            output_format="markdown",
            target_repository="https://docs.example.com",
            devex_trace_id=TRACE_ID,
        )
        assert result["success"] is True

    def test_p6_any_to_fail_on_bad_snapshot(self) -> None:
        pipe = DocPipeline()
        result = pipe.run_pipeline(
            codegraph_snapshot={"modules": [], "version": ""},
            api_spec={"openapi": "3.1.0", "paths": {"/health": {}}, "components": {"schemas": {}}},
            canon_version="1.0",
            output_format="markdown",
            target_repository="https://docs.example.com",
            devex_trace_id=TRACE_ID,
        )
        assert result["success"] is False
        assert "G-D1" in result.get("blocked_by", [])

    def test_pipeline_blocks_on_incomplete_spec(self) -> None:
        pipe = DocPipeline()
        result = pipe.run_pipeline(
            codegraph_snapshot={"modules": [{"name": "core"}], "version": "v1"},
            api_spec={"openapi": "", "paths": {}, "components": {"schemas": {}}},
            canon_version="1.0",
            output_format="markdown",
            target_repository="https://docs.example.com",
            devex_trace_id=TRACE_ID,
        )
        assert result["success"] is False
        assert "G-D2" in result.get("blocked_by", [])

    def test_pipeline_blocks_on_invalid_publish_target(self) -> None:
        pipe = DocPipeline()
        result = pipe.run_pipeline(
            codegraph_snapshot={"modules": [{"name": "core"}], "version": "v1"},
            api_spec={"openapi": "3.1.0", "paths": {"/health": {}}, "components": {"schemas": {"Health": {}}}},
            canon_version="1.0",
            output_format="markdown",
            target_repository="invalid://path",
            devex_trace_id=TRACE_ID,
        )
        assert result["success"] is False
        assert "G-D5" in result.get("blocked_by", [])

    def test_reset_returns_to_idle(self) -> None:
        pipe = DocPipeline()
        pipe.run_pipeline(
            codegraph_snapshot={"modules": [{"name": "core"}], "version": "v1"},
            api_spec={"openapi": "3.1.0", "paths": {"/health": {}}, "components": {"schemas": {}}},
            canon_version="1.0",
            output_format="markdown",
            target_repository="https://docs.example.com",
            devex_trace_id=TRACE_ID,
        )
        pipe.reset()
        assert pipe.stage == PipelineStage.IDLE


class TestDocPipelineGuards:
    """Test G-D1 through G-D5 guards individually."""

    def test_gd1_valid_snapshot_passes(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gd1_snapshot_valid({"modules": [{"name": "x"}], "version": "v1"})
        assert result["G-D1_snapshot_valid"] is True

    def test_gd1_empty_snapshot_fails(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gd1_snapshot_valid({"modules": [], "version": ""})
        assert result["G-D1_snapshot_valid"] is False

    def test_gd2_complete_spec_passes(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gd2_spec_complete({"openapi": "3.1.0", "paths": {"/h": {}}, "components": {"schemas": {"S": {}}}})
        assert result["G-D2_spec_complete"] is True

    def test_gd3_canon_100_passes(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gd3_canon_100({"compliance_pct": 100.0, "violations": []})
        assert result["G-D3_canon_100"] is True

    def test_gd4_ddg_pass_matches(self) -> None:
        pipe = DocPipeline()
        content = "test content"
        h = hashlib.sha256(content.encode()).hexdigest()
        result = pipe._guard_gd4_doc_deterministic(h, h)
        assert result["G-D4_doc_deterministic"] is True

    def test_gd4_ddg_fail_on_mismatch(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gd4_doc_deterministic("abc", "def")
        assert result["G-D4_doc_deterministic"] is False

    def test_gd5_valid_target_passes(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gd5_publish_target_valid("https://docs.example.com")
        assert result["G-D5_publish_target_valid"] is True

    def test_gd5_invalid_target_fails(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gd5_publish_target_valid("invalid://path")
        assert result["G-D5_publish_target_valid"] is False


class TestCLIRoutingGuards:
    """Test G-R1 through G-R5 CLI routing guards."""

    def test_gr1_f1_api_target_allows_readonly(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gr1_f1_api_target("status", "read_only")
        assert result["G-R1_f1_api_target"] is True

    def test_gr2_codegraph_readonly_allows_codegraph(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gr2_codegraph_read_only("codegraph_only")
        assert result["G-R2_codegraph_read_only"] is True

    def test_gr3_runtime_reachable_allows_when_online(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gr3_runtime_reachable(True, True)
        assert result["G-R3_runtime_reachable"] is True

    def test_gr3_blocks_when_runtime_unreachable(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gr3_runtime_reachable(True, False)
        assert result["G-R3_runtime_reachable"] is False

    def test_gr4_auth_valid_allows(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gr4_auth_token_valid(True)
        assert result["G-R4_auth_token_valid"] is True

    def test_gr4_auth_invalid_blocks(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gr4_auth_token_valid(False)
        assert result["G-R4_auth_token_valid"] is False

    def test_gr5_trace_id_injected_allows_valid(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gr5_trace_id_injected("dx_valid_trace_12345")
        assert result["G-R5_trace_id_injected"] is True

    def test_gr5_trace_id_missing_blocks(self) -> None:
        pipe = DocPipeline()
        result = pipe._guard_gr5_trace_id_injected("")
        assert result["G-R5_trace_id_injected"] is False

    def test_evaluate_cli_routing_allows_valid(self) -> None:
        pipe = DocPipeline()
        result = pipe.evaluate_cli_routing("status", "read_only", "dx_trace_123456789")
        assert result["decision"] == "allow"

    def test_evaluate_cli_routing_blocks_on_no_trace(self) -> None:
        pipe = DocPipeline()
        result = pipe.evaluate_cli_routing("replay", "f1_proxied", "")
        assert result["decision"] == "block"


class TestDeterministicDocGuard:
    """Test DDG determinism and idempotency."""

    def test_ddg_deterministic_same_inputs(self) -> None:
        pipe = DocPipeline()
        h1 = pipe._compute_ddg_hash("modules:A,B", "endpoints:1,2", "v1")
        h2 = pipe._compute_ddg_hash("modules:A,B", "endpoints:1,2", "v1")
        assert h1 == h2

    def test_ddg_changes_on_input_change(self) -> None:
        pipe = DocPipeline()
        h1 = pipe._compute_ddg_hash("modules:A,B", "endpoints:1,2", "v1")
        h2 = pipe._compute_ddg_hash("modules:A,C", "endpoints:1,2", "v1")
        assert h1 != h2

    def test_ddg_verify_passes(self) -> None:
        pipe = DocPipeline()
        content = "deterministic content"
        h = hashlib.sha256(content.encode()).hexdigest()
        assert pipe.ddg_verify(content, h) is True

    def test_ddg_verify_fails_on_tamper(self) -> None:
        pipe = DocPipeline()
        content = "original content"
        h = hashlib.sha256(content.encode()).hexdigest()
        assert pipe.ddg_verify("tampered content", h) is False

    def test_full_pipeline_ddg_matches(self) -> None:
        pipe = DocPipeline()
        r1 = pipe.run_pipeline(
            codegraph_snapshot={"modules": [{"name": "core"}], "version": "v1"},
            api_spec={"openapi": "3.1.0", "paths": {"/h": {}}, "components": {"schemas": {"S": {}}}},
            canon_version="1.0",
            output_format="markdown",
            target_repository="https://docs.example.com",
            devex_trace_id="dx_ddg_test",
        )
        assert r1["success"] is True
        assert r1["ddg"]["ddg_pass"] is True
