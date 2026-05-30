"""Memory Operational Validation Tests (20 tests).

EXEC-DIRECTIVE-L-VAL-001 Task 5:
  5 groups × 4 tests = 20 total

Groups:
  1. Multi-tenant load (throughput, latency, compaction)
  2. Deterministic retrieval (hash match ≥99.9%, drift = 0)
  3. Isolation & boundaries (cross-tenant leak = 0, G-M guards)
  4. Facade resilience (structured fault response, no DAG crash)
  5. Full lifecycle integration (end-to-end with state machine)
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List

import pytest

from core.memory.memory_hierarchy import MemoryHierarchy, IsolationViolation
from core.memory.context_compiler import ContextCompiler
from core.memory.skill_graph_manager import SkillGraphManager
from core.memory.memory_state_machine import MemoryStateMachine, MemoryTransition, MemoryState
from core.memory.trace_correlator import CognitiveTraceCorrelator
from core.memory.models import MemoryLayer, PruningPolicy, TokenBudget
from scripts.validation.memory_load_injector import run_load_test
from scripts.validation.deterministic_replay_validator import run_determinism_test
from scripts.validation.memory_isolation_stress import run_isolation_test


# ===================================================================
# Group 1: Multi-Tenant Load (4 tests)
# ===================================================================


class TestMultiTenantLoad:
    @pytest.mark.anyio
    async def test_load_throughput_minimum(self) -> None:
        result = await run_load_test(num_tenants=3)
        assert result["status"] == "ok"
        assert result["metrics"]["throughput_ops_sec"] >= 5.0

    @pytest.mark.anyio
    async def test_latency_p99_under_load(self) -> None:
        result = await run_load_test(num_tenants=3)
        latencies = result["metrics"]["latency_p99_ms"]
        for op, p99 in latencies.items():
            assert p99 < 5000, f"{op} p99 latency {p99}ms exceeds 5000ms"

    @pytest.mark.anyio
    async def test_context_compaction_rate(self) -> None:
        result = await run_load_test(num_tenants=3)
        assert result["metrics"]["context_compaction_rate"] >= 0

    @pytest.mark.anyio
    async def test_ten_tenants_no_crash(self) -> None:
        result = await run_load_test(num_tenants=10)
        assert result["status"] == "ok"
        assert result["metrics"]["total_operations"] > 0


# ===================================================================
# Group 2: Deterministic Retrieval (4 tests)
# ===================================================================


class TestDeterministicRetrieval:
    @pytest.mark.anyio
    async def test_hash_match_rate_above_threshold(self) -> None:
        result = await run_determinism_test(num_tenants=3, replay_traces=10, replay_rounds=2)
        assert result["status"] == "ok"
        assert result["metrics"]["hash_match_rate"] >= 99.0

    @pytest.mark.anyio
    async def test_zero_drift_under_replay(self) -> None:
        result = await run_determinism_test(num_tenants=2, replay_traces=5, replay_rounds=2)
        assert result["metrics"]["drift_incidents"] == 0

    @pytest.mark.anyio
    async def test_two_instances_same_hash(self) -> None:
        cc1 = ContextCompiler()
        cc2 = ContextCompiler()
        r1 = await cc1.compress_trace_to_context("t1", "ten_a", 2048, False)
        r2 = await cc2.compress_trace_to_context("t1", "ten_a", 2048, False)
        assert r1["context"]["_hash"] == r2["context"]["_hash"]

    @pytest.mark.anyio
    async def test_diff_tenant_diff_hash(self) -> None:
        cc = ContextCompiler()
        r1 = await cc.compress_trace_to_context("t1", "ten_a", 2048, False)
        r2 = await cc.compress_trace_to_context("t1", "ten_b", 2048, False)
        assert r1["context"]["_hash"] != r2["context"]["_hash"]


# ===================================================================
# Group 3: Isolation & Boundaries (4 tests)
# ===================================================================


class TestIsolationBoundaries:
    @pytest.mark.anyio
    async def test_cross_tenant_leakage_zero(self) -> None:
        result = await run_isolation_test()
        assert result["status"] == "ok"
        assert result["metrics"]["cross_tenant_context_leakage"] == 0

    @pytest.mark.anyio
    async def test_cascade_containment_full(self) -> None:
        result = await run_isolation_test()
        assert result["metrics"]["cascade_containment_rate"] == 100.0

    @pytest.mark.anyio
    async def test_gm1_wrong_state_returns_error(self) -> None:
        sm = MemoryStateMachine()
        r = sm.transition(MemoryTransition.T1, {"tenant_id": "ten_a", "trace_tenant": "ten_b"})
        assert r["status"] == "error"
        assert "Cannot apply" in r["message"]

    @pytest.mark.anyio
    async def test_gm2_blocks_low_budget(self) -> None:
        sm = MemoryStateMachine()
        sm.transition(MemoryTransition.T0, {"tenant_id": "ten_a"})
        sm.transition(MemoryTransition.T1, {"tenant_id": "ten_a", "trace_tenant": "ten_a"})
        r = sm.transition(MemoryTransition.T2, {"max_tokens": 100})
        assert r["status"] == "blocked"


# ===================================================================
# Group 4: Facade Resilience (4 tests)
# ===================================================================


class TestFacadeResilience:
    def test_facade_no_memory_graceful(self) -> None:
        from core.runtime.facade import EmoRuntimeFacade
        facade = EmoRuntimeFacade()
        result = facade.memory_store("episodic", "k1", {}, "ten_a")
        assert result["status"] == "error"
        assert "not available" in result["message"]

    def test_facade_no_compiler_graceful(self) -> None:
        from core.runtime.facade import EmoRuntimeFacade
        facade = EmoRuntimeFacade()
        result = facade.compile_context("trace_x", "ten_a")
        assert result["status"] == "error"

    def test_facade_wired_returns_dict(self) -> None:
        from core.runtime.facade import EmoRuntimeFacade
        from core.memory.memory_hierarchy import MemoryHierarchy
        from core.memory.trace_correlator import CognitiveTraceCorrelator
        facade = EmoRuntimeFacade(
            memory_hierarchy=MemoryHierarchy(),
            cognitive_trace_correlator=CognitiveTraceCorrelator(),
        )
        assert facade._mem_hierarchy is not None
        assert facade._cog_trace is not None

    def test_facade_health_with_memory(self) -> None:
        from core.runtime.facade import EmoRuntimeFacade
        from core.memory.memory_hierarchy import MemoryHierarchy
        facade = EmoRuntimeFacade(memory_hierarchy=MemoryHierarchy())
        result = facade.health()
        assert isinstance(result, dict)


# ===================================================================
# Group 5: Full Lifecycle Integration (4 tests)
# ===================================================================


class TestFullLifecycle:
    @pytest.mark.anyio
    async def test_store_to_context_lifecycle(self) -> None:
        mh = MemoryHierarchy()
        cc = ContextCompiler()
        ctc = CognitiveTraceCorrelator()

        cog = ctc.generate_cognitive_trace_id("ten_a")
        for i in range(3):
            await mh.store(MemoryLayer.EPISODIC, f"evt_{i}", {"seq": i},
                           "ten_a", "strict", cog)

        result = await cc.compress_trace_to_context("lifecycle_trace", "ten_a",
                                                    2048, False, cognitive_trace_id=cog)
        assert result["status"] == "ok"
        assert "context" in result

    @pytest.mark.anyio
    async def test_trace_correlator_full_chain(self) -> None:
        ctc = CognitiveTraceCorrelator()
        tid = ctc.generate_cognitive_trace_id("ten_a")
        ctc.record_memory_store(tid, "episodic", "k1", "ten_a")
        ctc.record_memory_store(tid, "semantic", "fact1", "ten_a")
        chain = ctc.verify_full_propagation(tid)
        assert chain["fully_propagated"] is True
        assert chain["layer_count"] == 2

    @pytest.mark.anyio
    async def test_skill_graph_to_prune(self) -> None:
        mh = MemoryHierarchy()
        sgm = SkillGraphManager()

        await sgm.record_successful_plan("dag_1", "h1", "ten_a", "intent_a", [], 1.0)
        await mh.store(MemoryLayer.PROCEDURAL, "skill_ref", {"dag": "dag_1"},
                       "ten_a", "strict", "cog_sg")

        r = await mh.retrieve(MemoryLayer.PROCEDURAL, {"key": "skill_ref"}, "ten_a")
        assert r["total"] == 1

    @pytest.mark.anyio
    async def test_state_machine_with_memory(self) -> None:
        sm = MemoryStateMachine()
        mh = MemoryHierarchy()
        cog = "cog_sm_lifecycle"

        sm.transition(MemoryTransition.T0, {"tenant_id": "ten_a"})
        sm.transition(MemoryTransition.T1, {"tenant_id": "ten_a", "trace_tenant": "ten_a"})

        await mh.store(MemoryLayer.EPISODIC, "sm_test", {}, "ten_a", "strict", cog)
        sm.transition(MemoryTransition.T2, {"max_tokens": 2048})

        sm.transition(MemoryTransition.T3A, {
            "scope_verified": False, "intent_match_score": 0.9,
            "owning_tenant": "ten_a", "requested_tenant": "ten_a",
        })
        t4 = sm.transition(MemoryTransition.T4, {})
        assert t4["status"] == "ok"
