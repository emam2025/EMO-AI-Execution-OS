"""Phase J1 — Developer Experience Layer Integration Tests.  # LAW-1 LAW-2 LAW-5 LAW-8 LAW-12 LAW-13 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Integration tests for SDKClient, CLIRuntime, DocGenerator, APISpecPublisher,
DocPipeline, and DevExTraceCorrelator.

GROUPS:
  TestF1RoutingEnforcement (5 tests): LAW 13 — NO direct ExecutionEngine access
  TestDocDeterminism (4 tests): DDG SHA-256 determinism
  TestTraceCorrelation (4 tests): devex_trace_id propagation
  TestSpecValidationSafety (4 tests): validation and rollback safety
  TestEventBusPropagation (4 tests): event hook coverage

Ref: artifacts/design/j1/protocols/01_devex_protocols.py
Ref: artifacts/design/j1/models/02_sdk_and_doc_models.py
Ref: artifacts/design/j1/03_doc_and_cli_pipeline.md
Ref: artifacts/design/j1/04_integration_blueprint.md
"""

from __future__ import annotations

import hashlib

import pytest

from core.devex.sdk_client import SDKClient
from core.devex.cli_runtime import CLIRuntime
from core.devex.doc_generator import DocGenerator
from core.devex.api_spec_publisher import APISpecPublisher
from core.devex.doc_pipeline import DocPipeline
from core.devex.trace_correlator import DevExTraceCorrelator
from core.runtime.event_bus import InMemoryEventBus


TRACE_ID = "dx_integration_test_001"


# ── TestF1RoutingEnforcement (5 tests) ────────────────────────


class TestF1RoutingEnforcement:
    """LAW 13: SDK/CLI MUST NOT access ExecutionEngine directly."""

    def test_sdk_does_not_import_execution_engine(self) -> None:
        import core.devex.sdk_client as sdk_mod
        import inspect
        source = inspect.getsource(sdk_mod)
        assert "ExecutionEngine" not in source
        assert "execution_engine" not in source.lower() or "import" not in [
            l for l in source.split("\n") if "execution_engine" in l.lower()
        ]

    def test_cli_routes_through_f1_not_direct(self) -> None:
        cli = CLIRuntime(strict_devex_mode=True)
        result = cli._evaluate_guards("replay", "f1_proxied", TRACE_ID)
        assert result["target_layer"] == "f1_unified_api"
        assert result["decision"] == "allow"

    def test_sdk_connect_requires_f1_endpoint(self) -> None:
        sdk = SDKClient(strict_devex_mode=True)
        with pytest.raises(ValueError, match="LAW 13"):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                async def _test():
                    await sdk.connect("http://insecure-endpoint", "token", TRACE_ID)
                try:
                    loop.run_until_complete(_test())
                except RuntimeError:
                    pass
            else:
                asyncio.run(sdk.connect("http://insecure-endpoint", "token", TRACE_ID))

    def test_cli_validate_architecture_reads_codegraph_only(self) -> None:
        cli = CLIRuntime(strict_devex_mode=True)
        import asyncio
        result = asyncio.run(cli.validate_architecture("/path/to/config", TRACE_ID))
        assert "codegraph_snapshot" in result
        assert result["valid"] is True

    def test_sdk_submit_routes_to_f1_not_execution(self) -> None:
        sdk = SDKClient(strict_devex_mode=True)
        import asyncio
        f1_mock = type("F1Mock", (), {"submit": lambda self, **kw: {"ticket_id": "f1_tkt_001", "status": "submitted"}})()
        sdk._f1 = f1_mock
        sdk._connected = True
        result = asyncio.run(sdk.submit_dag({"nodes": []}, {"tenant": "test"}, {}, TRACE_ID))
        assert result["ticket_id"] == "f1_tkt_001"


# ── TestDocDeterminism (4 tests) ──────────────────────────────


class TestDocDeterminism:
    """RULE 1: Same inputs -> same doc content_hash."""

    def test_render_canon_laws_deterministic(self) -> None:
        gen = DocGenerator()
        import asyncio
        r1 = asyncio.run(gen.render_canon_laws("1.0", "json", TRACE_ID))
        r2 = asyncio.run(gen.render_canon_laws("1.0", "json", TRACE_ID))
        assert r1["content_hash"] == r2["content_hash"]

    def test_render_canon_laws_diff_version_diff_hash(self) -> None:
        gen = DocGenerator()
        import asyncio
        r1 = asyncio.run(gen.render_canon_laws("1.0", "json", TRACE_ID))
        r2 = asyncio.run(gen.render_canon_laws("2.0", "json", TRACE_ID))
        assert r1["content_hash"] != r2["content_hash"]

    def test_extract_codegraph_deterministic(self) -> None:
        gen = DocGenerator()
        import asyncio
        snapshot = {"modules": [{"name": "A"}, {"name": "B"}], "interfaces": [], "edges": [], "version": "v1"}
        r1 = asyncio.run(gen.extract_codegraph_structure(snapshot, TRACE_ID))
        r2 = asyncio.run(gen.extract_codegraph_structure(snapshot, TRACE_ID))
        assert r1["component_count"] == r2["component_count"]
        assert r1["modules"] == r2["modules"]

    def test_generate_api_reference_deterministic(self) -> None:
        gen = DocGenerator()
        import asyncio
        spec = {"openapi": "3.1.0", "paths": {"/health": {}}, "components": {"schemas": {}}}
        r1 = asyncio.run(gen.generate_api_reference(spec, "openapi_json", TRACE_ID))
        r2 = asyncio.run(gen.generate_api_reference(spec, "openapi_json", TRACE_ID))
        assert r1["content_hash"] == r2["content_hash"]


# ── TestTraceCorrelation (4 tests) ────────────────────────────


class TestTraceCorrelation:
    """LAW 12: devex_trace_id propagates across all DevEx layers."""

    def test_sdk_to_doc_trace_propagation(self) -> None:
        corr = DevExTraceCorrelator()
        tid = corr.generate_devex_trace_id("integ_sess", "full_flow")
        corr.propagate_to_sdk(tid, "sdk_001")
        corr.propagate_to_doc(tid, "doc_001")
        corr.propagate_to_spec(tid, "spec_001")
        chain = corr.trace_chain(tid)
        assert "sdk" in chain["layers"]
        assert "doc_generator" in chain["layers"]
        assert "spec_publisher" in chain["layers"]

    def test_cli_to_f4_trace_propagation(self) -> None:
        corr = DevExTraceCorrelator()
        tid = corr.generate_devex_trace_id("cli_sess", "cli_logs")
        corr.propagate_to_cli(tid, "cli_001")
        corr.propagate_to_f1(tid, "f1_001")
        corr.propagate_to_f4(tid)
        chain = corr.trace_chain(tid)
        assert "f4_observability" in chain["layers"]

    def test_sdk_client_records_traces(self) -> None:
        corr = DevExTraceCorrelator()
        sdk = SDKClient(trace_correlator=corr)
        import asyncio
        asyncio.run(sdk.connect("https://runtime.example.com", "token", TRACE_ID))
        assert corr.correlation_for(TRACE_ID, "sdk_connect") != ""

    def test_cli_runtime_records_traces(self) -> None:
        corr = DevExTraceCorrelator()
        cli = CLIRuntime(trace_correlator=corr)
        import asyncio
        asyncio.run(cli.status("https://runtime.example.com", TRACE_ID))
        assert corr.correlation_for(TRACE_ID, "cli_status") != ""


# ── TestSpecValidationSafety (4 tests) ────────────────────────


class TestSpecValidationSafety:
    """RULE 3: Validation guards block invalid specs. RULE 5: Rollback."""

    def test_valid_spec_passes_validation(self) -> None:
        pub = APISpecPublisher()
        import asyncio
        result = asyncio.run(pub.validate_openapi_schema(
            {"openapi": "3.1.0", "paths": {"/h": {}}, "components": {"schemas": {"S": {}}}},
            TRACE_ID,
        ))
        assert result["valid"] is True

    def test_invalid_spec_fails_validation(self) -> None:
        pub = APISpecPublisher()
        import asyncio
        result = asyncio.run(pub.validate_openapi_schema(
            {"openapi": "2.0", "paths": {}, "components": {"schemas": {}}},
            TRACE_ID,
        ))
        assert result["valid"] is False

    def test_spec_rollback_restores_previous(self) -> None:
        pub = APISpecPublisher()
        import asyncio
        load_result = asyncio.run(pub.load_runtime_spec("4.5.0", TRACE_ID))
        spec_id = load_result["spec_id"]
        rollback_result = asyncio.run(pub.rollback_spec(spec_id, load_result["spec_hash"], TRACE_ID))
        assert rollback_result["rolled_back"] is True

    def test_spec_rollback_unknown_hash_fails(self) -> None:
        pub = APISpecPublisher()
        import asyncio
        result = asyncio.run(pub.rollback_spec("unknown_spec", "bad_hash", TRACE_ID))
        assert result["rolled_back"] is False


# ── TestEventBusPropagation (3 tests) ─────────────────────────


class TestEventBusPropagation:
    """LAW 5: All DevEx operations publish events."""

    def test_sdk_publishes_connect_event(self) -> None:
        bus = InMemoryEventBus()
        sdk = SDKClient(strict_devex_mode=True, event_bus=bus)
        import asyncio
        asyncio.run(sdk.connect("https://runtime.example.com", "token", TRACE_ID))
        events = bus.get_events("runtime.devex.sdk")
        assert len(events) >= 1
        assert events[0].payload["action"] == "SDKConnected"

    def test_cli_publishes_command_event(self) -> None:
        bus = InMemoryEventBus()
        cli = CLIRuntime(strict_devex_mode=True, event_bus=bus)
        import asyncio
        asyncio.run(cli.status("https://runtime.example.com", TRACE_ID))
        events = bus.get_events("runtime.devex.cli")
        assert len(events) >= 1

    def test_doc_publishes_publish_event(self) -> None:
        bus = InMemoryEventBus()
        gen = DocGenerator(strict_devex_mode=True, event_bus=bus)
        import asyncio
        asyncio.run(gen.render_canon_laws("1.0", "markdown", TRACE_ID))
        doc_id = f"canon_1_0_markdown_"
        result = asyncio.run(gen.publish_artifact("test_artifact", "https://docs.example.com", TRACE_ID))
        events = bus.get_events("runtime.devex.doc")
        assert len(events) >= 1

    def test_spec_publishes_publish_event(self) -> None:
        bus = InMemoryEventBus()
        pub = APISpecPublisher(strict_devex_mode=True, event_bus=bus)
        import asyncio
        asyncio.run(pub.load_runtime_spec("4.5.0", TRACE_ID))
        result = asyncio.run(pub.publish_async_events({"evt": {}}, "broker://mq", TRACE_ID))
        events = bus.get_events("runtime.devex.spec")
        assert len(events) >= 1
