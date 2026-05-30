"""Tests for DistributedScheduler — load-aware task → worker assignment."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.distributed_scheduler import DistributedScheduler, SCHEDULER_VERSION
from core.distributed_types import WorkerNode, WorkerStatus, TaskStatus
from core.worker_registry import WorkerRegistry
from core.execution_engine import PlanNode, ToolSpec


def test_version():
    assert SCHEDULER_VERSION == "1.0.0"


def test_version_property():
    reg = WorkerRegistry()
    sched = DistributedScheduler(reg)
    assert sched.version == "1.0.0"


def test_schedule_empty_nodes():
    reg = WorkerRegistry()
    sched = DistributedScheduler(reg)
    assignments, unassigned = sched.schedule([])
    assert assignments == []
    assert unassigned == []


def test_schedule_assigns_to_supporting_worker():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec], capacity=2,
    ))
    sched = DistributedScheduler(reg)
    nodes = [PlanNode(id="n1", tool="agent.explain")]
    assignments, unassigned = sched.schedule(nodes)
    assert len(assignments) == 1
    assert assignments[0].worker_id == "w1"
    assert assignments[0].tool == "agent.explain"
    assert unassigned == []


def test_schedule_unassigned_when_no_worker():
    reg = WorkerRegistry()
    sched = DistributedScheduler(reg)
    nodes = [PlanNode(id="n1", tool="agent.explain")]
    assignments, unassigned = sched.schedule(nodes)
    assert assignments == []
    assert len(unassigned) == 1


def test_schedule_unassigned_when_no_capability():
    reg = WorkerRegistry()
    other_spec = ToolSpec(name="graph_retrieval.ranked_hotspots")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[other_spec], capacity=2,
    ))
    sched = DistributedScheduler(reg)
    nodes = [PlanNode(id="n1", tool="agent.explain")]
    assignments, unassigned = sched.schedule(nodes)
    assert assignments == []
    assert len(unassigned) == 1


def test_schedule_respects_capacity():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec], capacity=1,
    ))
    sched = DistributedScheduler(reg)
    nodes = [
        PlanNode(id="n1", tool="agent.explain"),
        PlanNode(id="n2", tool="agent.explain"),
    ]
    assignments, unassigned = sched.schedule(nodes)
    assert len(assignments) == 1  # only 1 can fit
    assert len(unassigned) == 1


def test_schedule_load_balances():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec], capacity=2,
    ))
    reg.register(WorkerNode(
        id="w2", url="http://localhost:9002",
        tools=[spec], capacity=2,
    ))
    sched = DistributedScheduler(reg)
    nodes = [
        PlanNode(id="n1", tool="agent.explain"),
        PlanNode(id="n2", tool="agent.explain"),
    ]
    assignments, unassigned = sched.schedule(nodes)
    assert len(assignments) == 2
    assert unassigned == []
    # Each worker should get 1 task (least-loaded first)
    worker_ids = [a.worker_id for a in assignments]
    assert "w1" in worker_ids
    assert "w2" in worker_ids


def test_schedule_mixed_tools():
    reg = WorkerRegistry()
    spec1 = ToolSpec(name="agent.explain")
    spec2 = ToolSpec(name="graph_retrieval.ranked_hotspots")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec1, spec2], capacity=4,
    ))
    sched = DistributedScheduler(reg)
    nodes = [
        PlanNode(id="n1", tool="agent.explain"),
        PlanNode(id="n2", tool="graph_retrieval.ranked_hotspots"),
    ]
    assignments, unassigned = sched.schedule(nodes)
    assert len(assignments) == 2
    assert unassigned == []


def test_release_decrements_load():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    w = WorkerNode(id="w1", url="http://localhost:9001", tools=[spec], capacity=2)
    reg.register(w)
    sched = DistributedScheduler(reg)
    nodes = [PlanNode(id="n1", tool="agent.explain")]
    assignments, _ = sched.schedule(nodes)
    assert reg.get("w1").current_load == 1
    sched.release(assignments[0])
    assert reg.get("w1").current_load == 0


def test_schedule_tag_affinity():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec], capacity=2, tags={"region": "us-east"},
    ))
    # also register a worker without the tag
    reg.register(WorkerNode(
        id="w2", url="http://localhost:9002",
        tools=[spec], capacity=2, tags={"region": "eu-west"},
    ))
    sched = DistributedScheduler(reg, tag_affinity={"region": "us-east"})
    nodes = [
        PlanNode(id="n1", tool="agent.explain"),
        PlanNode(id="n2", tool="agent.explain"),
        PlanNode(id="n3", tool="agent.explain"),
    ]
    assignments, unassigned = sched.schedule(nodes)
    # Phase 1 assigns to w1 (first any_worker_for → w1)
    # Phase 2 assigns more to w1 (available_capacity)
    # Phase 3 tag-affinity finds w1 again
    # So w1 gets 2, w2 gets 1
    assert len(unassigned) == 0
    assert len(assignments) == 3


def test_schedule_increments_load_for_each_assignment():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec], capacity=5,
    ))
    sched = DistributedScheduler(reg)
    nodes = [PlanNode(id=f"n{i}", tool="agent.explain") for i in range(3)]
    sched.schedule(nodes)
    assert reg.get("w1").current_load == 3


def test_task_assignment_has_unique_ids():
    reg = WorkerRegistry()
    spec = ToolSpec(name="agent.explain")
    reg.register(WorkerNode(
        id="w1", url="http://localhost:9001",
        tools=[spec], capacity=5,
    ))
    sched = DistributedScheduler(reg)
    nodes = [PlanNode(id=f"n{i}", tool="agent.explain") for i in range(3)]
    assignments, _ = sched.schedule(nodes)
    task_ids = {a.task_id for a in assignments}
    assert len(task_ids) == 3  # all unique
