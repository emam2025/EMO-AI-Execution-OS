"""Tests for ServiceRegistry — local/remote tool endpoint routing."""
import sys, os, json, threading, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.service_registry import (
    ServiceRegistry, LocalEndpoint, RemoteEndpoint,
)
from core.execution_engine import ToolSpec


# ── Helpers ─────────────────────────────────────────────────────

def sample_fn(x: int = 0, y: int = 0) -> dict:
    return {"sum": x + y, "product": x * y}


class FnWithState:
    def __init__(self):
        self.call_count = 0
    def __call__(self, **kw):
        self.call_count += 1
        return {"called": self.call_count, **kw}


# ── LocalEndpoint ───────────────────────────────────────────────

def test_local_endpoint_execute():
    ep = LocalEndpoint("add", sample_fn, ToolSpec(name="add"))
    result = ep.execute({"x": 3, "y": 4})
    assert result == {"sum": 7, "product": 12}


def test_local_endpoint_none_result():
    def returns_none(**kw):
        return None
    ep = LocalEndpoint("void", returns_none, ToolSpec(name="void"))
    assert ep.execute({}) == {}


# ── ServiceRegistry basic ───────────────────────────────────────

def test_register_and_execute_local():
    sr = ServiceRegistry()
    sr.register_local("add", sample_fn)
    assert sr.can_execute("add") is True
    assert sr.can_execute("nonexistent") is False
    result = sr.execute("add", {"x": 10, "y": 20})
    assert result == {"sum": 30, "product": 200}


def test_execute_unregistered():
    sr = ServiceRegistry()
    try:
        sr.execute("nope", {})
        assert False, "Should raise KeyError"
    except KeyError:
        pass


def test_registered_tools():
    sr = ServiceRegistry()
    sr.register_local("a", sample_fn)
    sr.register_local("b", sample_fn)
    tools = sr.registered_tools()
    assert tools == {"a": "local", "b": "local"}


def test_unregister():
    sr = ServiceRegistry()
    sr.register_local("a", sample_fn)
    assert sr.can_execute("a") is True
    sr.unregister("a")
    assert sr.can_execute("a") is False


def test_clear():
    sr = ServiceRegistry()
    sr.register_local("a", sample_fn)
    sr.register_local("b", sample_fn)
    sr.clear()
    assert sr.registered_tools() == {}


# ── ToolSpec association ────────────────────────────────────────

def test_get_spec():
    spec = ToolSpec(name="add", timeout_seconds=15.0)
    sr = ServiceRegistry()
    sr.register_local("add", sample_fn, spec)
    assert sr.get_spec("add") is spec
    assert sr.get_spec("nope") is None


# ── Thread safety ───────────────────────────────────────────────

def test_concurrent_execution():
    sr = ServiceRegistry()
    fn = FnWithState()
    sr.register_local("stateful", fn)

    errors = []
    def call_it():
        try:
            for _ in range(50):
                sr.execute("stateful", {"call": 1})
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=call_it) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0
    assert fn.call_count == 200


# ── RemoteEndpoint (mocked HTTP) ─────────────────────────────────

def _make_mock_response(data, status=200):
    """Create a mock urllib response."""
    class MockResponse:
        def __init__(self, data, status):
            self.data = json.dumps(data).encode("utf-8")
            self.status = status
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
    return MockResponse(data, status)


def test_remote_endpoint_get_status(monkeypatch):
    ep = RemoteEndpoint("test", "http://worker:9001",
                        ToolSpec(name="test", timeout_seconds=5.0))
    def mock_urlopen(url, **kw):
        assert "/health" in str(url)
        return _make_mock_response({
            "status": "ok", "version": "1.0.0",
            "load": 0.5, "tools_count": 10, "leased_tasks": 2,
        })
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    status = ep.get_status()
    assert status["status"] == "ok"
    assert status["version"] == "1.0.0"
    assert status["load"] == 0.5


def test_remote_endpoint_capabilities(monkeypatch):
    ep = RemoteEndpoint("test", "http://worker:9001",
                        ToolSpec(name="test", timeout_seconds=5.0))
    def mock_urlopen(url, **kw):
        assert "/capabilities" in str(url)
        return _make_mock_response([
            {"name": "agent.explain", "version": "1.0.0"},
            {"name": "graph_retrieval.ranked_hotspots", "version": "1.0.0"},
        ])
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    caps = ep.capabilities()
    assert len(caps) == 2
    assert caps[0]["name"] == "agent.explain"


def test_remote_endpoint_supports_tool(monkeypatch):
    ep = RemoteEndpoint("test", "http://worker:9001",
                        ToolSpec(name="test", timeout_seconds=5.0))
    def mock_urlopen(url, **kw):
        return _make_mock_response([
            {"name": "agent.explain", "version": "1.0.0"},
        ])
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    assert ep.supports_tool("agent.explain") is True
    assert ep.supports_tool("agent.explain", "1.0.0") is True
    assert ep.supports_tool("agent.explain", "2.0.0") is False
    assert ep.supports_tool("nonexistent") is False


def test_remote_endpoint_supports_tool_on_error(monkeypatch):
    ep = RemoteEndpoint("test", "http://worker:9001",
                        ToolSpec(name="test", timeout_seconds=5.0))
    def mock_urlopen(url, **kw):
        raise urllib.error.URLError("Connection refused")
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    assert ep.supports_tool("anything") is False


def test_remote_endpoint_execute_with_lease_context(monkeypatch):
    ep = RemoteEndpoint("test", "http://worker:9001",
                        ToolSpec(name="test", timeout_seconds=5.0))
    def mock_urlopen(req, **kw):
        body = json.loads(req.data)
        assert body["context"]["lease_id"] == "lease_123"
        assert body["context"]["execution_id"] == "exec_456"
        assert body["context"]["attempt_number"] == 1
        assert body["inputs"] == {"x": 42}
        return _make_mock_response({"result": "ok"})
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    result = ep.execute(
        {"x": 42},
        lease_id="lease_123",
        execution_id="exec_456",
        attempt_number=1,
    )
    assert result == {"result": "ok"}


def test_remote_endpoint_execute_url_includes_execute_path(monkeypatch):
    ep = RemoteEndpoint("test", "http://worker:9001",
                        ToolSpec(name="test", timeout_seconds=5.0))
    def mock_urlopen(req, **kw):
        assert req.get_full_url() == "http://worker:9001/execute"
        return _make_mock_response({"ok": True})
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    ep.execute({})


def test_remote_endpoint_connection_refused(monkeypatch):
    ep = RemoteEndpoint("remote", "http://127.0.0.1:18999/exec",
                        ToolSpec(name="remote", timeout_seconds=2.0))
    try:
        ep.execute({"x": 1})
        assert False, "Should raise"
    except (RuntimeError, OSError):
        pass
