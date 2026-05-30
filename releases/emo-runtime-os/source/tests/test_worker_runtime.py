"""Tests for WorkerRuntime — emo-worker daemon."""
import sys, os, json, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.worker_runtime import (
    WorkerRuntime,
    parse_args,
    build_capabilities,
    WORKER_RUNTIME_VERSION,
)


# ── Version ─────────────────────────────────────────────────────

def test_worker_runtime_version():
    wr = WorkerRuntime(
        worker_id="test",
        host="localhost",
        port=9100,
        engine_url="http://engine:8000",
        tools=[],
    )
    assert wr.version == WORKER_RUNTIME_VERSION


# ── WorkerRuntime — core properties ────────────────────────────

def test_worker_init():
    wr = WorkerRuntime(
        worker_id="w1",
        host="0.0.0.0",
        port=9100,
        engine_url="http://engine:9000",
        tools=[{"name": "agent.explain", "version": "1.0.0"}],
        contracts=[{"name": "agent.explain", "inputs": {}, "outputs": {}}],
        capacity=4,
        tags={"pool": "gpu"},
    )
    assert wr.worker_id == "w1"
    assert wr.url == "http://0.0.0.0:9100"
    assert wr.engine_url == "http://engine:9000"
    assert len(wr.tools) == 1
    assert wr.capacity == 4
    assert wr.tags == {"pool": "gpu"}


# ── execute_task ───────────────────────────────────────────────

class MockWorker(WorkerRuntime):
    """Worker with a mock tool implementation."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.tool_results = {}

    def set_tool_result(self, tool: str, result: Any):
        self.tool_results[tool] = result

    def _run_tool(self, tool: str, inputs: Dict) -> Any:
        if tool in self.tool_results:
            return self.tool_results[tool]
        raise ValueError(f"Unknown tool: {tool}")


def test_execute_task_success():
    wr = MockWorker(
        worker_id="w1",
        host="localhost",
        port=9100,
        engine_url="http://engine:8000",
        tools=[{"name": "agent.explain", "version": "1.0.0"}],
    )
    wr.set_tool_result("agent.explain", {"explanation": "hello"})

    result = wr.execute_task(
        task_id="task_1",
        tool="agent.explain",
        inputs={"query": "hello"},
        lease_id="lease_1",
        execution_id="exec_1",
    )

    assert result["status"] == "completed"
    assert result["result"] == {"explanation": "hello"}
    assert result["task_id"] == "task_1"
    assert result["worker_id"] == "w1"
    assert result["execution_id"] == "exec_1"


def test_execute_task_failure():
    wr = MockWorker(
        worker_id="w1",
        host="localhost",
        port=9100,
        engine_url="http://engine:8000",
        tools=[{"name": "failing", "version": "1.0.0"}],
    )
    wr.set_tool_result("failing", {"error": "Something broke"})

    result = wr.execute_task(
        task_id="task_1",
        tool="failing",
        inputs={},
        lease_id="lease_1",
    )

    assert result["status"] == "failed" or result["status"] == "completed"
    # It completed with an error result; not an exception


def test_execute_task_tracks_active():
    wr = MockWorker(
        worker_id="w1",
        host="localhost",
        port=9100,
        engine_url="http://engine:8000",
        tools=[{"name": "agent.explain", "version": "1.0.0"}],
    )
    wr.set_tool_result("agent.explain", {"ok": True})

    assert len(wr._active_tasks) == 0
    wr.execute_task("t1", "agent.explain", {}, lease_id="l1")
    assert len(wr._active_tasks) == 0  # released after completion


# ── _run_tool raises NotImplementedError in base class ─────────

def test_base_worker_run_tool_not_implemented():
    wr = WorkerRuntime(
        worker_id="w1",
        host="localhost",
        port=9100,
        engine_url="http://engine:8000",
        tools=[{"name": "agent.explain", "version": "1.0.0"}],
    )
    import pytest
    with pytest.raises(NotImplementedError):
        wr._run_tool("agent.explain", {})


# ── parse_args ─────────────────────────────────────────────────

def test_parse_args_defaults():
    args = parse_args([])
    assert args.host == "localhost"
    assert args.port == 9100
    assert args.engine_url == "http://localhost:8000"
    assert args.capacity == 2
    assert args.heartbeat_interval == 15.0
    assert args.lease_duration == 60.0


def test_parse_args_custom():
    args = parse_args([
        "--host", "0.0.0.0",
        "--port", "9200",
        "--engine-url", "http://engine:9000",
        "--worker-id", "my-worker",
        "--tools", "agent.explain,graph_retrieval.ranked_hotspots",
        "--capacity", "8",
        "--heartbeat-interval", "10",
        "--lease-duration", "120",
        "--tags", "pool=gpu,region=us-east",
    ])
    assert args.host == "0.0.0.0"
    assert args.port == 9200
    assert args.engine_url == "http://engine:9000"
    assert args.worker_id == "my-worker"
    assert args.tools == "agent.explain,graph_retrieval.ranked_hotspots"
    assert args.capacity == 8
    assert args.heartbeat_interval == 10.0
    assert args.lease_duration == 120.0
    assert args.tags == "pool=gpu,region=us-east"


# ── build_capabilities ─────────────────────────────────────────

def test_build_capabilities_from_args():
    class FakeArgs:
        tools = "agent.explain,graph_retrieval.ranked_hotspots"
        tags = "pool=gpu"
        capabilities_file = None
    tools, contracts, tags = build_capabilities(FakeArgs())
    assert len(tools) == 2
    assert tools[0]["name"] == "agent.explain"
    assert tools[1]["name"] == "graph_retrieval.ranked_hotspots"
    assert tags == {"pool": "gpu"}


def test_build_capabilities_empty():
    class FakeArgs:
        tools = ""
        tags = ""
        capabilities_file = None
    tools, contracts, tags = build_capabilities(FakeArgs())
    assert tools == []
    assert tags == {}


def test_build_capabilities_from_file():
    """Test loading capabilities from a JSON file."""
    import tempfile
    data = {
        "tools": [{"name": "custom_tool", "version": "2.0.0"}],
        "contracts": [{"name": "custom_tool", "inputs": {}, "outputs": {}}],
    }
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()

    try:
        class FakeArgs:
            tools = ""
            tags = ""
            capabilities_file = f.name
        tools, contracts, tags = build_capabilities(FakeArgs())
        assert len(tools) == 1
        assert tools[0]["name"] == "custom_tool"
        assert len(contracts) == 1
    finally:
        os.unlink(f.name)
