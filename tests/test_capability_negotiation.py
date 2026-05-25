"""Tests for CapabilityNegotiator — worker ↔ engine compatibility."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.capability_negotiation import (
    CapabilityNegotiator, WorkerCapability, CapabilityReport,
    CAPABILITY_NEGOTIATION_VERSION,
)
from core.contracts import SUPPORTED_SCHEMA_VERSIONS
from core.worker_registry import WorkerRegistry


# ── Helpers ─────────────────────────────────────────────────────

def _make_capabilities(**overrides) -> WorkerCapability:
    defaults = dict(
        tools=[
            {"name": "agent.explain", "version": "1.0.0"},
            {"name": "graph_retrieval.ranked_hotspots", "version": "1.0.0"},
        ],
        contracts=[
            {
                "name": "agent.explain",
                "inputs": {"query": "string"},
                "outputs": {"explanation": "string"},
            },
        ],
        schema_versions=["1.0.0"],
        runtime_version="1.0.0",
        worker_id="worker_1",
        url="http://worker:9001",
        capacity=2,
        tags={"pool": "gpu"},
    )
    defaults.update(overrides)
    return WorkerCapability(**defaults)


# ── Version ─────────────────────────────────────────────────────

def test_version():
    n = CapabilityNegotiator()
    assert n.version == CAPABILITY_NEGOTIATION_VERSION


# ── Schema checks ───────────────────────────────────────────────

def test_schema_compatible():
    n = CapabilityNegotiator()
    caps = _make_capabilities(schema_versions=["1.0.0"])
    report = n.validate(caps)
    assert report.schema_compatible is True
    assert report.compatible is True


def test_schema_incompatible():
    n = CapabilityNegotiator(supported_schema_versions={"2.0.0"})
    caps = _make_capabilities(schema_versions=["1.0.0"])
    report = n.validate(caps)
    assert report.schema_compatible is False
    assert report.compatible is False
    assert any("do not overlap" in r for r in report.reasons)


def test_schema_empty():
    n = CapabilityNegotiator()
    caps = _make_capabilities(schema_versions=[])
    report = n.validate(caps)
    assert report.schema_compatible is False
    assert report.compatible is False


# ── Tool checks ─────────────────────────────────────────────────

def test_required_tools_available():
    n = CapabilityNegotiator(
        required_tools=["agent.explain", "graph_retrieval.ranked_hotspots"],
    )
    caps = _make_capabilities()
    report = n.validate(caps)
    assert report.tools_compatible is True
    assert report.compatible is True


def test_required_tools_missing():
    n = CapabilityNegotiator(
        required_tools=["agent.explain", "nonexistent.tool"],
    )
    caps = _make_capabilities()
    report = n.validate(caps)
    assert report.tools_compatible is False
    assert report.compatible is False
    assert any("nonexistent.tool" in r for r in report.reasons)


def test_extra_tools_warn():
    n = CapabilityNegotiator(required_tools=["agent.explain"])
    caps = _make_capabilities()
    report = n.validate(caps)
    assert report.tools_compatible is True
    assert len(report.warnings) >= 1  # warns about extra tool


# ── Contract checks ─────────────────────────────────────────────

def test_contracts_well_formed():
    caps = _make_capabilities()
    n = CapabilityNegotiator()
    report = n.validate(caps)
    assert report.contracts_compatible is True


def test_contracts_malformed_inputs():
    caps = _make_capabilities(
        contracts=[{"name": "bad", "inputs": "not_a_dict", "outputs": {}}],
    )
    n = CapabilityNegotiator()
    report = n.validate(caps)
    assert report.contracts_compatible is False
    assert report.compatible is False


def test_contracts_malformed_outputs():
    caps = _make_capabilities(
        contracts=[{"name": "bad", "inputs": {}, "outputs": "not_a_dict"}],
    )
    n = CapabilityNegotiator()
    report = n.validate(caps)
    assert report.contracts_compatible is False


# ── Runtime version checks ──────────────────────────────────────

def test_runtime_compatible():
    n = CapabilityNegotiator(min_runtime_version="1.0.0")
    caps = _make_capabilities(runtime_version="1.0.0")
    report = n.validate(caps)
    assert report.runtime_compatible is True


def test_runtime_incompatible():
    n = CapabilityNegotiator(min_runtime_version="1.5.0")
    caps = _make_capabilities(runtime_version="1.0.0")
    report = n.validate(caps)
    assert report.runtime_compatible is False
    assert report.compatible is False


# ── Overall compatibility ───────────────────────────────────────

def test_fully_compatible():
    n = CapabilityNegotiator(
        required_tools=["agent.explain"],
        min_runtime_version="1.0.0",
    )
    caps = _make_capabilities()
    report = n.validate(caps)
    assert report.compatible is True


def test_report_includes_supported_tools():
    n = CapabilityNegotiator()
    caps = _make_capabilities()
    report = n.validate(caps)
    assert "agent.explain" in report.supported_tools
    assert "graph_retrieval.ranked_hotspots" in report.supported_tools


def test_report_includes_supported_versions():
    n = CapabilityNegotiator()
    caps = _make_capabilities(schema_versions=["1.0.0", "2.0.0"])
    report = n.validate(caps)
    assert "1.0.0" in report.supported_versions


# ── register_if_compatible ──────────────────────────────────────

def test_register_if_compatible_ok():
    n = CapabilityNegotiator(
        required_tools=["agent.explain"],
        min_runtime_version="1.0.0",
    )
    registry = WorkerRegistry()
    caps = _make_capabilities()
    report = n.register_if_compatible(caps, registry)
    assert report.compatible is True
    assert registry.worker_count() == 1
    worker = registry.get("worker_1")
    assert worker is not None
    assert worker.url == "http://worker:9001"


def test_register_if_compatible_rejects():
    n = CapabilityNegotiator(
        required_tools=["missing_tool"],
    )
    registry = WorkerRegistry()
    caps = _make_capabilities()
    report = n.register_if_compatible(caps, registry)
    assert report.compatible is False
    assert registry.worker_count() == 0
