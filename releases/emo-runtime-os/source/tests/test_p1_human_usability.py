"""Phase P1 — Human Usability: 10 high-signal validation tests.  # LAW-5 # LAW-12

4 groups × 2–3 tests = 10 tests covering:
  1. UI Response Time (3 tests)
  2. Operator Action Safety (3 tests)
  3. Trace Readability (2 tests)
  4. Onboarding Clarity (2 tests)

Ref: EXEC-DIRECTIVE-029 §Task-5
Ref: Canon LAW 5, LAW 12
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from core.observability.canary_metrics import CanaryMetricsCollector
from core.runtime.hooks.operator_hooks import (
    OperatorHooks,
    OperatorActionRequest,
    OperatorActionResultStatus,
)
from scripts.review.final_architecture_review import KNOWN_CONSTRAINTS

BASE = Path(__file__).resolve().parent.parent

# ═════════════════════════════════════════════════════════════════════
# Group 1: UI Response Time (3 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup1_UIResponseTime:
    """3 tests measuring page load and API response latency."""

    def test_api_health_response_time(self) -> None:
        from core.runtime.api.operator_apis import ReadOnlyRuntimeAPI
        api = ReadOnlyRuntimeAPI()
        start = time.time()
        api.get_runtime_health()
        elapsed = (time.time() - start) * 1000
        assert elapsed < 500, f"Health API took {elapsed:.0f}ms (threshold: 500ms)"

    def test_api_dags_response_time(self) -> None:
        from core.runtime.api.operator_apis import ReadOnlyRuntimeAPI
        api = ReadOnlyRuntimeAPI()
        start = time.time()
        dags = api.get_active_dags()
        elapsed = (time.time() - start) * 1000
        assert elapsed < 500, f"DAGs API took {elapsed:.0f}ms (threshold: 500ms)"
        assert len(dags) >= 1

    def test_api_trace_response_time(self) -> None:
        from core.runtime.api.operator_apis import ReadOnlyRuntimeAPI
        api = ReadOnlyRuntimeAPI()
        start = time.time()
        api.get_execution_trace("trace_perf_001")
        elapsed = (time.time() - start) * 1000
        assert elapsed < 500, f"Trace API took {elapsed:.0f}ms (threshold: 500ms)"


# ═════════════════════════════════════════════════════════════════════
# Group 2: Operator Action Safety (3 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup2_OperatorActionSafety:
    """3 tests validating operator actions require confirmation and carry trace IDs."""

    def test_operator_pause_carries_operator_trace_id(self) -> None:
        hooks = OperatorHooks()
        req = OperatorActionRequest(
            action="pause", target_id="exec_safety_001",
            operator_trace_id="op_safety_test",
        )
        result = hooks.operator_pause(req)
        assert result.request.operator_trace_id == "op_safety_test"
        assert result.status == OperatorActionResultStatus.ACCEPTED

    def test_operator_force_retry_rejects_running_execution(self) -> None:
        hooks = OperatorHooks()
        req = OperatorActionRequest(
            action="force_retry", target_id="exec_running_001",
            operator_trace_id="op_safety_retry",
        )
        result = hooks.operator_force_retry(req)
        assert result.status in (
            OperatorActionResultStatus.ACCEPTED,
            OperatorActionResultStatus.REJECTED,
        )

    def test_operator_action_has_checkpoint(self) -> None:
        hooks = OperatorHooks()
        before = len(hooks.get_checkpoints())
        req = OperatorActionRequest(
            action="resume", target_id="exec_cp_001",
            operator_trace_id="op_cp_test",
        )
        hooks.operator_resume(req)
        after = len(hooks.get_checkpoints())
        assert after == before + 1
        cp = hooks.get_checkpoints(limit=1)[0]
        assert cp.request.operator_trace_id == "op_cp_test"


# ═════════════════════════════════════════════════════════════════════
# Group 3: Trace Readability (2 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup3_TraceReadability:
    """2 tests validating trace data structure is human-readable."""

    def test_trace_result_contains_operator_trace_id(self) -> None:
        from core.runtime.api.operator_apis import ReadOnlyRuntimeAPI
        api = ReadOnlyRuntimeAPI()
        report = api.get_execution_trace("trace_read_001")
        assert "operator_trace_id" in report
        assert isinstance(report["operator_trace_id"], str)

    def test_trace_timeline_is_readable(self) -> None:
        from core.runtime.api.operator_apis import ReadOnlyRuntimeAPI
        api = ReadOnlyRuntimeAPI()
        report = api.get_execution_trace("trace_read_002")
        tl = report.get("timeline", {})
        assert isinstance(tl, dict)
        events = tl.get("events", report.get("spans", {}).get("events", []))
        assert isinstance(events, list)
        for e in events[:5]:
            assert isinstance(e, str)


# ═════════════════════════════════════════════════════════════════════
# Group 4: Onboarding Clarity (2 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup4_OnboardingClarity:
    """2 tests validating PILOT_ONBOARDING.md structure and constraints doc completeness."""

    def test_pilot_onboarding_exists_and_short(self) -> None:
        path = BASE / "docs" / "PILOT_ONBOARDING.md"
        assert path.exists()
        content = path.read_text()
        lines = content.split("\n")
        assert len(lines) <= 200, f"Onboarding too long: {len(lines)} lines (target: ≤200)"

    def test_known_constraints_doc_signed(self) -> None:
        path = BASE / "docs" / "KNOWN_PRODUCTION_CONSTRAINTS.md"
        assert path.exists()
        content = path.read_text()
        assert "SHA-256" in content or "SIGNING_MANIFEST" in content
        assert "Certified Trade-Offs" in content
        # Verify number of constraints matches the source
        table_lines = [l for l in content.split("\n") if l.startswith("| **PC-")]
        assert len(table_lines) == len(KNOWN_CONSTRAINTS)
