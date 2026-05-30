"""Phase 14 tests: Execution Memory Layer.

Tests cover:
  - Session lifecycle: create, complete, fail, rollback, get, recent
  - Session events: add, sequence ordering, fetch
  - Reasoning traces: add, query by session, query by type
  - Task memory: create, update, find, complete, fail
  - Plan history: create, succeed, fail, task_plans, latest_plan
  - Integration: end-to-end workflow with all layers
"""

import sys, os, time, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)


# ======================================================================
# Fixtures
# ======================================================================

from core.execution_memory import (
    ExecutionMemory,
    ExecutionSession,
    SessionEvent,
    ReasoningTrace,
    TaskRecord,
    PlanAttempt,
)


def make_memory():
    path = os.path.join(tempfile.mkdtemp(), "test_phase14.db")
    m = ExecutionMemory(path)
    m.clear()
    return m


# ======================================================================
# 1 – Session Lifecycle Tests
# ======================================================================


def test_session_create():
    m = make_memory()
    sid = m.create_session("find auth function", strategy="balanced")
    assert sid is not None
    session = m.get_session(sid)
    assert session is not None
    assert session.query == "find auth function"
    assert session.strategy == "balanced"
    assert session.status == "active"
    assert session.completed_at is None


def test_session_complete():
    m = make_memory()
    sid = m.create_session("find auth function")
    m.complete_session(sid, {"top_symbol": "validate"}, feedback=0.9)
    session = m.get_session(sid)
    assert session.status == "completed"
    assert session.completed_at is not None
    assert session.feedback == 0.9
    assert session.result_summary == {"top_symbol": "validate"}


def test_session_fail():
    m = make_memory()
    sid = m.create_session("find auth function")
    m.fail_session(sid, "Graph unavailable")
    session = m.get_session(sid)
    assert session.status == "failed"
    assert session.result_summary == {"error": "Graph unavailable"}


def test_session_rollback():
    m = make_memory()
    sid = m.create_session("find auth function")
    m.rollback_session(sid, "Precision collapse")
    session = m.get_session(sid)
    assert session.status == "rolled_back"
    assert session.result_summary == {"reason": "Precision collapse"}


def test_session_not_found():
    m = make_memory()
    session = m.get_session("nonexistent")
    assert session is None


def test_session_recent():
    m = make_memory()
    ids = []
    for i in range(5):
        sid = m.create_session(f"query_{i}")
        ids.append(sid)
        time.sleep(0.01)
    recent = m.recent_sessions(limit=3)
    assert len(recent) == 3
    assert recent[0].query == "query_4"


def test_session_recent_with_status():
    m = make_memory()
    s1 = m.create_session("q1")
    s2 = m.create_session("q2")
    m.complete_session(s2)
    s3 = m.create_session("q3")
    m.fail_session(s3)
    active = m.recent_sessions(limit=10, status="active")
    assert len(active) == 1  # only s1 stays active
    assert all(s.status == "active" for s in active)


def test_session_metadata():
    m = make_memory()
    sid = m.create_session("query", strategy="test_file",
                            metadata={"repo_size": 1200, "file": "auth.py"})
    session = m.get_session(sid)
    assert session.metadata["repo_size"] == 1200
    assert session.metadata["file"] == "auth.py"


# ======================================================================
# 2 – Session Events Tests
# ======================================================================


def test_event_add_and_fetch():
    m = make_memory()
    sid = m.create_session("test query")
    eid1 = m.add_event(sid, "retrieval", {"symbols": ["s1", "s2"]})
    eid2 = m.add_event(sid, "plan", {"steps": 3})
    eid3 = m.add_event(sid, "action", {"tool": "explain"})
    assert eid1 > 0
    assert eid2 > eid1
    assert eid3 > eid2
    events = m.session_events(sid)
    assert len(events) == 3
    assert events[0].event_type == "retrieval"
    assert events[0].detail["symbols"] == ["s1", "s2"]
    assert events[1].event_type == "plan"
    assert events[2].event_type == "action"


def test_event_sequence_ordering():
    m = make_memory()
    sid = m.create_session("test")
    m.add_event(sid, "first")
    m.add_event(sid, "second")
    m.add_event(sid, "third")
    events = m.session_events(sid)
    assert len(events) == 3
    assert events[0].sequence == 1
    assert events[0].event_type == "first"
    assert events[1].sequence == 2
    assert events[1].event_type == "second"
    assert events[2].sequence == 3
    assert events[2].event_type == "third"


def test_event_empty_session():
    m = make_memory()
    sid = m.create_session("empty")
    events = m.session_events(sid)
    assert events == []


def test_event_multiple_sessions():
    m = make_memory()
    s1 = m.create_session("s1")
    s2 = m.create_session("s2")
    m.add_event(s1, "e1")
    m.add_event(s2, "e2")
    m.add_event(s1, "e3")
    assert len(m.session_events(s1)) == 2
    assert len(m.session_events(s2)) == 1


# ======================================================================
# 3 – Reasoning Trace Tests
# ======================================================================


def test_reasoning_add():
    m = make_memory()
    sid = m.create_session("test")
    tid = m.add_reasoning(sid, "symbol_selection", "s1",
                           "Highest importance score",
                           {"score": 8.5, "incoming_calls": 5})
    assert tid > 0
    traces = m.session_reasoning(sid)
    assert len(traces) == 1
    assert traces[0].trace_type == "symbol_selection"
    assert traces[0].target_id == "s1"
    assert traces[0].reason == "Highest importance score"
    assert traces[0].evidence["score"] == 8.5


def test_reasoning_multiple_types():
    m = make_memory()
    sid = m.create_session("test")
    m.add_reasoning(sid, "symbol_selection", "s1", "high importance")
    m.add_reasoning(sid, "weight_change", "balanced", "semantic drift")
    m.add_reasoning(sid, "refactor_suggestion", "s2", "high complexity")
    traces = m.session_reasoning(sid)
    assert len(traces) == 3


def test_reasoning_by_type():
    m = make_memory()
    s1 = m.create_session("q1")
    s2 = m.create_session("q2")
    m.add_reasoning(s1, "symbol_selection", "s1", "important")
    m.add_reasoning(s2, "symbol_selection", "s2", "critical")
    m.add_reasoning(s1, "weight_change", "balanced", "drift")
    traces = m.reasoning_by_type("symbol_selection")
    assert len(traces) == 2
    traces = m.reasoning_by_type("weight_change")
    assert len(traces) == 1


def test_reasoning_empty():
    m = make_memory()
    sid = m.create_session("empty")
    assert m.session_reasoning(sid) == []


# ======================================================================
# 4 – Task Memory Tests
# ======================================================================


def test_task_create():
    m = make_memory()
    tid = m.create_task(
        "refactor auth flow",
        symbols=["s1", "s2"],
        files=["auth.py", "middleware.py"],
        impact_chain=["auth.py -> middleware.py -> api.py"],
    )
    assert tid is not None
    task = m.get_task(tid)
    assert task is not None
    assert task.description == "refactor auth flow"
    assert "s1" in task.symbols
    assert "auth.py" in task.files
    assert task.status == "active"
    assert task.created_at > 0


def test_task_update():
    m = make_memory()
    tid = m.create_task("test task")
    m.update_task(tid, symbols=["s3", "s4"], files=["new.py"])
    task = m.get_task(tid)
    assert "s3" in task.symbols
    assert "s4" in task.symbols
    assert "new.py" in task.files


def test_task_find():
    m = make_memory()
    m.create_task("refactor auth flow")
    m.create_task("implement login page")
    m.create_task("fix database connection")
    results = m.find_tasks("auth")
    assert len(results) >= 1
    assert "auth" in results[0].description


def test_task_complete():
    m = make_memory()
    tid = m.create_task("test task")
    m.complete_task(tid)
    task = m.get_task(tid)
    assert task.status == "completed"


def test_task_fail():
    m = make_memory()
    tid = m.create_task("test task")
    m.fail_task(tid, {"reason": "dependency missing"})
    task = m.get_task(tid)
    assert task.status == "failed"
    assert task.metadata["reason"] == "dependency missing"


def test_task_not_found():
    m = make_memory()
    task = m.get_task("nonexistent")
    assert task is None


# ======================================================================
# 5 – Plan History Tests
# ======================================================================


def test_plan_create():
    m = make_memory()
    sid = m.create_session("test session")
    tid = m.create_task("test task")
    pid = m.create_plan(sid, tid, [{"action": "explain", "target": "s1"}])
    assert pid is not None
    plan = m.get_plan(pid)
    assert plan is not None
    assert plan.status == "proposed"
    assert plan.plan_number == 1
    assert plan.steps == [{"action": "explain", "target": "s1"}]


def test_plan_succeed():
    m = make_memory()
    sid = m.create_session("test")
    tid = m.create_task("test")
    pid = m.create_plan(sid, tid, [{"action": "explain"}])
    m.succeed_plan(pid, {"summary": "done", "symbols": 3})
    plan = m.get_plan(pid)
    assert plan.status == "succeeded"
    assert plan.completed_at is not None
    assert plan.result["summary"] == "done"


def test_plan_fail():
    m = make_memory()
    sid = m.create_session("test")
    tid = m.create_task("test")
    pid = m.create_plan(sid, tid, [{"action": "explain"}])
    m.fail_plan(pid, "Graph not available")
    plan = m.get_plan(pid)
    assert plan.status == "failed"
    assert plan.error == "Graph not available"


def test_plan_auto_increment():
    m = make_memory()
    sid = m.create_session("test")
    tid = m.create_task("test")
    p1 = m.create_plan(sid, tid, [{"action": "a"}])
    p2 = m.create_plan(sid, tid, [{"action": "b"}])
    p3 = m.create_plan(sid, tid, [{"action": "c"}])
    plan1 = m.get_plan(p1)
    plan2 = m.get_plan(p2)
    plan3 = m.get_plan(p3)
    assert plan1.plan_number == 1
    assert plan2.plan_number == 2
    assert plan3.plan_number == 3


def test_plan_task_plans():
    m = make_memory()
    sid = m.create_session("s1")
    tid = m.create_task("test")
    m.create_plan(sid, tid, [{"step": 1}])
    m.create_plan(sid, tid, [{"step": 2}])
    plans = m.task_plans(tid)
    assert len(plans) == 2
    assert plans[0].plan_number == 2  # DESC order


def test_plan_session_plans():
    m = make_memory()
    sid = m.create_session("s1")
    tid1 = m.create_task("t1")
    tid2 = m.create_task("t2")
    m.create_plan(sid, tid1, [{"action": "a"}])
    m.create_plan(sid, tid2, [{"action": "b"}])
    plans = m.session_plans(sid)
    assert len(plans) == 2


def test_plan_latest():
    m = make_memory()
    sid = m.create_session("test")
    tid = m.create_task("test")
    m.create_plan(sid, tid, [{"step": 1}])
    m.create_plan(sid, tid, [{"step": 2}])
    latest = m.latest_plan(tid)
    assert latest is not None
    assert latest.plan_number == 2


def test_plan_latest_none():
    m = make_memory()
    latest = m.latest_plan("nonexistent")
    assert latest is None


# ======================================================================
# 6 – Integration Tests
# ======================================================================


def test_integration_full_workflow():
    """End-to-end: session → events → reasoning → task → plans."""
    m = make_memory()

    # 1. Session
    sid = m.create_session("refactor auth flow", strategy="balanced",
                            metadata={"source": "user_query"})

    # 2. Events (ordered)
    m.add_event(sid, "retrieval", {"symbols_found": 5, "top": "s1"})
    m.add_event(sid, "plan", {"steps": 3, "tools": ["explain", "impact"]})
    m.add_event(sid, "action", {"tool": "explain", "target": "s1"})
    m.add_event(sid, "result", {"summary": "auth flow explained"})

    # 3. Reasoning
    m.add_reasoning(sid, "symbol_selection", "s1",
                     "Highest importance score",
                     {"importance": 8.5, "incoming_calls": 12})
    m.add_reasoning(sid, "tool_choice", "explain",
                     "User asked for explanation",
                     {"intent": "explain"})

    # 4. Complete session with feedback
    m.complete_session(sid, {"symbols_explained": 3}, feedback=0.85)

    # 5. Create task
    tid = m.create_task(
        "refactor auth flow",
        symbols=["s1", "s2", "s3"],
        files=["auth.py", "middleware.py"],
        impact_chain=["auth.py → middleware.py → api.py"],
    )

    # 6. Plans for the task
    p1 = m.create_plan(sid, tid, [
        {"action": "explain", "target": "auth"},
        {"action": "impact", "target": "auth"},
    ])
    m.succeed_plan(p1, {"symbols": 3, "files": 2})

    p2 = m.create_plan(sid, tid, [
        {"action": "refactor", "target": "auth"},
    ])
    m.fail_plan(p2, "Missing dependencies")

    # ── Verify everything ──

    session = m.get_session(sid)
    assert session.status == "completed"
    assert session.feedback == 0.85
    assert session.metadata["source"] == "user_query"

    events = m.session_events(sid)
    assert len(events) == 4
    assert events[0].event_type == "retrieval"
    assert events[1].event_type == "plan"
    assert events[2].event_type == "action"
    assert events[3].event_type == "result"

    traces = m.session_reasoning(sid)
    assert len(traces) == 2
    assert traces[0].trace_type == "symbol_selection"
    assert traces[1].trace_type == "tool_choice"

    task = m.get_task(tid)
    assert task.status == "active"
    assert len(task.symbols) == 3
    assert len(task.files) == 2

    plans = m.task_plans(tid)
    assert len(plans) == 2
    assert plans[1].status == "succeeded"
    assert plans[0].status == "failed"

    # Latest plan
    latest = m.latest_plan(tid)
    assert latest.plan_number == 2
    assert latest.status == "failed"


def test_integration_multiple_sessions_same_task():
    """Multiple sessions can contribute plans to the same task."""
    m = make_memory()
    tid = m.create_task("fix bug")

    s1 = m.create_session("first attempt")
    p1 = m.create_plan(s1, tid, [{"fix": "approach_a"}])
    m.fail_plan(p1, "Regression")

    s2 = m.create_session("second attempt")
    p2 = m.create_plan(s2, tid, [{"fix": "approach_b"}])
    m.succeed_plan(p2, {"fixed": True})

    plans = m.task_plans(tid)
    assert len(plans) == 2
    assert plans[1].status == "failed"
    assert plans[0].status == "succeeded"


def test_integration_clear():
    m = make_memory()
    sid = m.create_session("test")
    tid = m.create_task("test")
    m.create_plan(sid, tid, [])
    m.add_reasoning(sid, "symbol_selection", "s1", "reason")
    m.add_event(sid, "retrieval")
    m.clear()
    assert m.get_session(sid) is None
    assert m.get_task(tid) is None
    assert len(m.session_events(sid)) == 0
    assert len(m.session_reasoning(sid)) == 0


# ======================================================================
# Run all
# ======================================================================

if __name__ == "__main__":
    tests = [
        # Session lifecycle
        ("session create", test_session_create),
        ("session complete", test_session_complete),
        ("session fail", test_session_fail),
        ("session rollback", test_session_rollback),
        ("session not found", test_session_not_found),
        ("session recent", test_session_recent),
        ("session recent with status", test_session_recent_with_status),
        ("session metadata", test_session_metadata),
        # Session events
        ("event add and fetch", test_event_add_and_fetch),
        ("event sequence ordering", test_event_sequence_ordering),
        ("event empty session", test_event_empty_session),
        ("event multiple sessions", test_event_multiple_sessions),
        # Reasoning traces
        ("reasoning add", test_reasoning_add),
        ("reasoning multiple types", test_reasoning_multiple_types),
        ("reasoning by type", test_reasoning_by_type),
        ("reasoning empty", test_reasoning_empty),
        # Task memory
        ("task create", test_task_create),
        ("task update", test_task_update),
        ("task find", test_task_find),
        ("task complete", test_task_complete),
        ("task fail", test_task_fail),
        ("task not found", test_task_not_found),
        # Plan history
        ("plan create", test_plan_create),
        ("plan succeed", test_plan_succeed),
        ("plan fail", test_plan_fail),
        ("plan auto increment", test_plan_auto_increment),
        ("plan task plans", test_plan_task_plans),
        ("plan session plans", test_plan_session_plans),
        ("plan latest", test_plan_latest),
        ("plan latest none", test_plan_latest_none),
        # Integration
        ("full workflow", test_integration_full_workflow),
        ("multi-session same task", test_integration_multiple_sessions_same_task),
        ("clear all", test_integration_clear),
    ]

    passed = 0
    failed = 0
    for desc, test_fn in tests:
        try:
            test_fn()
            print(f"  ✓ {desc}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {desc}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    total = len(tests)
    print(f"\n{'='*50}")
    print(f"Phase 14: {passed} passed, {failed} failed, {total} total")
    print(f"{'✓ COMPLETE' if failed == 0 else '✗ NEEDS FIX'}")
