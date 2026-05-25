"""Tests for Distributed Execution types + WorkerRegistry."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.distributed_types import (
    WorkerNode, WorkerStatus, TaskAssignment, TaskStatus,
    WORKER_HEARTBEAT_INTERVAL, WORKER_TIMEOUT, DISTRIBUTED_VERSION,
)
from core.worker_registry import WorkerRegistry
from core.execution_engine import ToolSpec


# ═══════════════════════════════════════════════════════════════════
# distributed_types tests
# ═══════════════════════════════════════════════════════════════════

def test_distributed_version():
    assert DISTRIBUTED_VERSION == "1.0.0"


def test_worker_node_default_status():
    w = WorkerNode(id="w1", url="http://localhost:9001")
    assert w.status == WorkerStatus.IDLE
    assert w.capacity == 1
    assert w.current_load == 0
    assert w.version == DISTRIBUTED_VERSION


def test_available_capacity():
    w = WorkerNode(id="w1", url="http://localhost:9001", capacity=4, current_load=1)
    assert w.available_capacity == 3


def test_is_available_idle_with_capacity():
    w = WorkerNode(id="w1", url="http://localhost:9001", capacity=2, current_load=0)
    assert w.is_available is True


def test_is_available_false_when_busy():
    w = WorkerNode(id="w1", url="http://localhost:9001", capacity=2, current_load=2)
    assert w.is_available is False


def test_is_available_false_when_offline():
    w = WorkerNode(id="w1", url="http://localhost:9001", status=WorkerStatus.OFFLINE)
    assert w.is_available is False


def test_supports_tool():
    spec = ToolSpec(name="agent.explain")
    w = WorkerNode(id="w1", url="http://localhost:9001", tools=[spec])
    assert w.supports_tool("agent.explain") is True
    assert w.supports_tool("nonexistent") is False


def test_can_execute_with_version():
    from core.contracts import ToolContract
    contract = ToolContract(tool_name="agent.explain", version="1.0.0")
    spec = ToolSpec(name="agent.explain", contract=contract)
    w = WorkerNode(id="w1", url="http://localhost:9001", tools=[spec])
    assert w.can_execute("agent.explain", "1.0.0") is True
    assert w.can_execute("agent.explain", "2.0.0") is False


def test_task_assignment_defaults():
    ta = TaskAssignment(task_id="t1", tool="agent.explain",
                        inputs={"symbol_id": "foo"}, worker_id="w1")
    assert ta.status == TaskStatus.PENDING
    assert ta.result is None
    assert ta.error is None


def test_worker_status_enum_values():
    assert WorkerStatus.IDLE.value == "idle"
    assert WorkerStatus.BUSY.value == "busy"
    assert WorkerStatus.OFFLINE.value == "offline"
    assert WorkerStatus.UNKNOWN.value == "unknown"


def test_task_status_enum_values():
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.TIMEOUT.value == "timeout"


# ═══════════════════════════════════════════════════════════════════
# WorkerRegistry tests
# ═══════════════════════════════════════════════════════════════════

def test_register_worker():
    reg = WorkerRegistry()
    w = WorkerNode(id="w1", url="http://localhost:9001")
    reg.register(w)
    assert reg.worker_count() == 1
    assert reg.get("w1") is not None


def test_register_worker_sets_idle_and_heartbeat():
    reg = WorkerRegistry()
    w = WorkerNode(id="w1", url="http://localhost:9001", status=WorkerStatus.OFFLINE)
    reg.register(w)
    stored = reg.get("w1")
    assert stored is not None
    assert stored.status == WorkerStatus.IDLE
    assert stored.last_heartbeat > 0


def test_unregister_worker():
    reg = WorkerRegistry()
    reg.register(WorkerNode(id="w1", url="http://localhost:9001"))
    removed = reg.unregister("w1")
    assert removed is not None
    assert removed.id == "w1"
    assert reg.worker_count() == 0


def test_unregister_nonexistent():
    reg = WorkerRegistry()
    assert reg.unregister("nonexistent") is None


def test_heartbeat_updates_timestamp():
    reg = WorkerRegistry()
    reg.register(WorkerNode(id="w1", url="http://localhost:9001"))
    old_ts = reg.get("w1").last_heartbeat
    time.sleep(0.001)
    result = reg.heartbeat("w1")
    assert result is True
    assert reg.get("w1").last_heartbeat > old_ts


def test_heartbeat_nonexistent():
    reg = WorkerRegistry()
    assert reg.heartbeat("nobody") is False


def test_list_workers():
    reg = WorkerRegistry()
    reg.register(WorkerNode(id="w1", url="http://localhost:9001"))
    reg.register(WorkerNode(id="w2", url="http://localhost:9002"))
    workers = reg.list_workers()
    assert len(workers) == 2


def test_available_workers_filters_by_tool():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec], capacity=2,
    ))
    reg.register(WorkerNode(
        id="w2", url="http://localhost:9002",
        tools=[], capacity=2,
    ))
    available = reg.available_workers("agent.explain")
    assert len(available) == 1
    assert available[0].id == "w1"


def test_available_workers_excludes_busy():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec], capacity=1, current_load=1,
    ))
    available = reg.available_workers("agent.explain")
    assert len(available) == 0


def test_any_worker_for_returns_least_loaded():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec], capacity=4, current_load=3,
    ))
    reg.register(WorkerNode(
        id="w2", url="http://localhost:9002",
        tools=[spec], capacity=4, current_load=1,
    ))
    best = reg.any_worker_for("agent.explain")
    assert best is not None
    assert best.id == "w2"


def test_any_worker_for_nonexistent_tool():
    reg = WorkerRegistry()
    assert reg.any_worker_for("nonexistent") is None


def test_prune_offline_removes_stale():
    reg = WorkerRegistry()
    w = WorkerNode(id="w1", url="http://localhost:9001")
    w.last_heartbeat = time.time() - 200  # expired — set BEFORE register overwrites
    reg.register(w)
    # register sets heartbeat but we can force it again after registration
    reg.get("w1").last_heartbeat = time.time() - 200
    pruned = reg.prune_offline(timeout=100)
    assert pruned == 1
    assert reg.worker_count() == 0


def test_prune_offline_keeps_recent():
    reg = WorkerRegistry()
    reg.register(WorkerNode(id="w1", url="http://localhost:9001"))
    pruned = reg.prune_offline(timeout=100)
    assert pruned == 0
    assert reg.worker_count() == 1


def test_mark_offline():
    reg = WorkerRegistry()
    reg.register(WorkerNode(id="w1", url="http://localhost:9001"))
    result = reg.mark_offline("w1")
    assert result is True
    assert reg.get("w1").status == WorkerStatus.OFFLINE


def test_mark_offline_nonexistent():
    reg = WorkerRegistry()
    assert reg.mark_offline("nobody") is False


def test_increment_load():
    reg = WorkerRegistry()
    w = WorkerNode(id="w1", url="http://localhost:9001", capacity=2)
    reg.register(w)
    reg.increment_load("w1")
    assert reg.get("w1").current_load == 1
    assert reg.get("w1").status == WorkerStatus.IDLE


def test_increment_load_becomes_busy():
    reg = WorkerRegistry()
    w = WorkerNode(id="w1", url="http://localhost:9001", capacity=1)
    reg.register(w)
    reg.increment_load("w1")
    assert reg.get("w1").status == WorkerStatus.BUSY


def test_decrement_load():
    reg = WorkerRegistry()
    w = WorkerNode(id="w1", url="http://localhost:9001", capacity=2, current_load=2)
    reg.register(w)
    reg.decrement_load("w1")
    assert reg.get("w1").current_load == 1


def test_decrement_load_becomes_idle():
    reg = WorkerRegistry()
    w = WorkerNode(id="w1", url="http://localhost:9001", capacity=2, current_load=1)
    reg.register(w)
    reg.decrement_load("w1")
    assert reg.get("w1").current_load == 0
    assert reg.get("w1").status == WorkerStatus.IDLE


def test_increment_decrement_nonexistent():
    reg = WorkerRegistry()
    assert reg.increment_load("nobody") is False
    assert reg.decrement_load("nobody") is False


def test_workers_by_tag():
    reg = WorkerRegistry()
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tags={"region": "us-east", "gpu": "true"},
    ))
    reg.register(WorkerNode(
        id="w2", url="http://localhost:9002",
        tags={"region": "eu-west"},
    ))
    us = reg.workers_by_tag("region", "us-east")
    assert len(us) == 1
    assert us[0].id == "w1"
    eu = reg.workers_by_tag("region", "eu-west")
    assert len(eu) == 1
    assert eu[0].id == "w2"


def test_worker_count_empty():
    reg = WorkerRegistry()
    assert reg.worker_count() == 0
