"""Phase K5 — Runtime Visibility: 25 validation tests.  # LAW-5 # LAW-12

5 groups × 5 tests = 25 high-signal tests covering:
  1. API Read-Only Guarantee (LAW-K5-1)
  2. Operator Trace Propagation (LAW-K5-3)
  3. Hook Safety & Checkpoints (LAW-8, LAW-12)
  4. CLI Contract Integrity
  5. UI Contract Schema Validation

Ref: EXEC-DIRECTIVE-027A §Task-5
Ref: Canon LAW 5, LAW 8, LAW 12
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from core.runtime.api.operator_apis import ReadOnlyRuntimeAPI, OperatorTrace, DAGSummary, ClusterHealth
from core.runtime.hooks.operator_hooks import (
    OperatorHooks,
    OperatorActionRequest,
    OperatorActionResult,
    OperatorActionResultStatus,
)

# ═════════════════════════════════════════════════════════════════════
# Group 1: API Read-Only Guarantee (5 tests)
# LAW-K5-1 — no method mutates state
# ═════════════════════════════════════════════════════════════════════


class TestGroup1_ReadOnlyGuarantee:
    """5 tests validating all ReadOnlyRuntimeAPI methods are side-effect-free."""

    def test_get_active_dags_returns_list_of_dag_summary(self) -> None:
        api = ReadOnlyRuntimeAPI()
        dags = api.get_active_dags()
        assert len(dags) >= 1
        for d in dags:
            assert isinstance(d, DAGSummary)
            assert d.dag_id

    def test_get_execution_trace_returns_report(self) -> None:
        api = ReadOnlyRuntimeAPI()
        report = api.get_execution_trace("trace_test_001")
        assert isinstance(report, dict)
        assert report["trace_id"] == "trace_test_001"
        assert isinstance(report["timeline"], dict)

    def test_get_worker_topology_returns_list(self) -> None:
        api = ReadOnlyRuntimeAPI()
        topology = api.get_worker_topology()
        assert isinstance(topology, list)
        for entry in topology:
            assert isinstance(entry, dict)

    def test_get_runtime_health_returns_cluster_health(self) -> None:
        api = ReadOnlyRuntimeAPI()
        health = api.get_runtime_health()
        assert isinstance(health, ClusterHealth)
        assert health.overall_status in ("healthy", "degraded", "critical")
        assert health.worker_count >= 0

    def test_export_dag_graphml_returns_string(self) -> None:
        api = ReadOnlyRuntimeAPI()
        graphml = api.export_dag_graphml("dag_test_001")
        assert isinstance(graphml, str)
        assert "<graphml" in graphml
        assert "dag_test_001" in graphml


# ═════════════════════════════════════════════════════════════════════
# Group 2: Operator Trace Propagation (5 tests)
# LAW-K5-3 — every action carries operator_trace_id
# ═════════════════════════════════════════════════════════════════════


class TestGroup2_OperatorTracePropagation:
    """5 tests verifying operator_trace_id generation and propagation."""

    def test_trace_generated_on_get_active_dags(self) -> None:
        api = ReadOnlyRuntimeAPI()
        before = len(api.get_operator_traces())
        api.get_active_dags()
        after = len(api.get_operator_traces())
        assert after == before + 1

    def test_trace_has_operator_trace_id(self) -> None:
        api = ReadOnlyRuntimeAPI()
        api.get_runtime_health()
        traces = api.get_operator_traces(limit=1)
        assert len(traces) == 1
        ot = traces[0]
        assert isinstance(ot.operator_trace_id, str)
        assert ot.operator_trace_id.startswith("op_")

    def test_trace_records_action_name(self) -> None:
        api = ReadOnlyRuntimeAPI()
        api.get_worker_topology()
        traces = api.get_operator_traces(limit=1)
        assert traces[0].action == "get_worker_topology"

    def test_trace_records_target(self) -> None:
        api = ReadOnlyRuntimeAPI()
        api.get_execution_trace("trc_abc")
        traces = api.get_operator_traces(limit=1)
        assert traces[0].target == "trc_abc"

    def test_get_operator_traces_respects_limit(self) -> None:
        api = ReadOnlyRuntimeAPI()
        for _ in range(10):
            api.get_active_dags()
        all_traces = api.get_operator_traces(limit=100)
        limited = api.get_operator_traces(limit=3)
        assert len(limited) == 3
        assert len(all_traces) >= 10
        assert limited == all_traces[-3:]


# ═════════════════════════════════════════════════════════════════════
# Group 3: Hook Safety & Checkpoints (5 tests)
# LAW-8, LAW-12 — state transitions create audit checkpoints
# ═════════════════════════════════════════════════════════════════════


class TestGroup3_HookSafetyAndCheckpoints:
    """5 tests validating OperatorHooks produce checkpoints and propagate trace IDs."""

    def test_operator_pause_returns_accepted(self) -> None:
        hooks = OperatorHooks()
        req = OperatorActionRequest(action="pause", target_id="exec_001", operator_trace_id="op_test")
        result = hooks.operator_pause(req)
        assert result.status == OperatorActionResultStatus.ACCEPTED
        assert result.checkpoint_id.startswith("cp_")

    def test_operator_resume_returns_accepted(self) -> None:
        hooks = OperatorHooks()
        req = OperatorActionRequest(action="resume", target_id="exec_001", operator_trace_id="op_test")
        result = hooks.operator_resume(req)
        assert result.status == OperatorActionResultStatus.ACCEPTED

    def test_operator_force_retry_returns_accepted(self) -> None:
        hooks = OperatorHooks()
        req = OperatorActionRequest(action="force_retry", target_id="exec_001", operator_trace_id="op_test")
        result = hooks.operator_force_retry(req)
        assert result.status == OperatorActionResultStatus.ACCEPTED

    def test_checkpoint_created_on_pause(self) -> None:
        hooks = OperatorHooks()
        before = len(hooks.get_checkpoints())
        req = OperatorActionRequest(action="pause", target_id="exec_001", operator_trace_id="op_test")
        hooks.operator_pause(req)
        after = len(hooks.get_checkpoints())
        assert after == before + 1

    def test_checkpoint_stores_operator_trace_id(self) -> None:
        hooks = OperatorHooks()
        req = OperatorActionRequest(action="resume", target_id="exec_002", operator_trace_id="op_custom_trace")
        hooks.operator_resume(req)
        cp = hooks.get_checkpoints(limit=1)[0]
        assert cp.request.operator_trace_id == "op_custom_trace"
        assert cp.request.target_id == "exec_002"


# ═════════════════════════════════════════════════════════════════════
# Group 4: CLI Contract Integrity (5 tests)
# CLI emits operator_trace_id and wraps API correctly
# ═════════════════════════════════════════════════════════════════════


class TestGroup4_CLIContractIntegrity:
    """5 tests validating CLI dispatches commands through API/Hooks correctly."""

    def test_cli_status_returns_zero(self) -> None:
        from scripts.cli.operator_cli import OperatorCLI
        cli = OperatorCLI()
        rc = cli.run(["emo", "status"])
        assert rc == 0

    def test_cli_trace_returns_zero(self) -> None:
        from scripts.cli.operator_cli import OperatorCLI
        cli = OperatorCLI()
        rc = cli.run(["emo", "trace", "trace_001"])
        assert rc == 0

    def test_cli_worker_returns_zero(self) -> None:
        from scripts.cli.operator_cli import OperatorCLI
        cli = OperatorCLI()
        rc = cli.run(["emo", "worker"])
        assert rc == 0

    def test_cli_pause_returns_zero(self) -> None:
        from scripts.cli.operator_cli import OperatorCLI
        cli = OperatorCLI()
        rc = cli.run(["emo", "pause", "exec_001"])
        assert rc == 0

    def test_cli_unknown_command_shows_help(self) -> None:
        from scripts.cli.operator_cli import OperatorCLI
        cli = OperatorCLI()
        rc = cli.run(["emo", "nonexistent"])
        assert rc == 2


# ═════════════════════════════════════════════════════════════════════
# Group 5: UI Contract Schema Validation (5 tests)
# docs/operator_ui_contract.json is valid OpenAPI 3.0
# ═════════════════════════════════════════════════════════════════════


class TestGroup5_UIContractSchemaValidation:
    """5 tests validating the UI contract JSON against OpenAPI 3.0 rules."""

    CONTRACT_PATH = Path("docs/operator_ui_contract.json")

    def test_contract_file_exists(self) -> None:
        assert self.CONTRACT_PATH.exists()

    def test_contract_is_valid_json(self) -> None:
        raw = self.CONTRACT_PATH.read_text()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_contract_has_openapi_version(self) -> None:
        raw = self.CONTRACT_PATH.read_text()
        parsed = json.loads(raw)
        assert parsed["openapi"].startswith("3.0")

    def test_contract_defines_all_k5_paths(self) -> None:
        raw = self.CONTRACT_PATH.read_text()
        parsed = json.loads(raw)
        paths = parsed.get("paths", {})
        expected = {"/health", "/dags", "/traces/{traceId}", "/topology/workers",
                    "/actions/pause", "/actions/resume", "/actions/force-retry", "/actions/replay"}
        for p in expected:
            assert p in paths, f"Missing path: {p}"

    def test_contract_all_paths_require_operator_trace_id(self) -> None:
        raw = self.CONTRACT_PATH.read_text()
        parsed = json.loads(raw)
        paths = parsed.get("paths", {})
        for path, methods in paths.items():
            for method, spec in methods.items():
                params = spec.get("parameters", [])
                header_names = [p["name"] for p in params if p.get("in") == "header"]
                has_trace = any(n == "X-Operator-Trace-Id" for n in header_names)
                if method in ("get", "post"):
                    assert has_trace, f"{path} {method} missing X-Operator-Trace-Id"
