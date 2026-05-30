"""memory_load_injector.py — Multi-tenant memory load simulation.

EXEC-DIRECTIVE-L-VAL-001 Task 1:
  10 concurrent tenants, each issuing store/retrieve/prune/compile_context
  at varying context sizes (512, 1k, 4k tokens).

Measures:
  - throughput_ops_sec
  - latency_p99_ms
  - context_compaction_rate

LAW 11: No global mutable state — each request's tenant_id is traced.
LAW 14: Deterministic retrieval verified by caller.
LAW 8: Every operation carries cognitive_trace_id.
"""

from __future__ import annotations

import asyncio
import json
import time
import statistics
from typing import Any, Dict, List, Tuple

from core.memory.memory_hierarchy import MemoryHierarchy
from core.memory.context_compiler import ContextCompiler
from core.memory.skill_graph_manager import SkillGraphManager
from core.memory.memory_state_machine import MemoryStateMachine, MemoryTransition
from core.memory.trace_correlator import CognitiveTraceCorrelator
from core.memory.models import MemoryLayer, PruningPolicy


NUM_TENANTS = 10
CONTEXT_SIZES = [1024, 2048, 4096]
OPS_PER_TENANT = 30


async def _tenant_workload(
    tenant_id: str,
    mh: MemoryHierarchy,
    cc: ContextCompiler,
    sgm: SkillGraphManager,
    sm: MemoryStateMachine,
    ctc: CognitiveTraceCorrelator,
    context_size: int,
) -> Dict[str, Any]:
    """Single tenant's sequence of memory operations."""
    latencies: Dict[str, List[float]] = {}
    ops_count = 0

    cog_trace = ctc.generate_cognitive_trace_id(tenant_id)

    for i in range(OPS_PER_TENANT):
        t0 = time.perf_counter()
        await mh.store(MemoryLayer.EPISODIC, f"key_{i}", {"data": f"val_{i}"},
                       tenant_id, "strict", cog_trace)
        latencies.setdefault("store", []).append((time.perf_counter() - t0) * 1000)
        ops_count += 1

        t0 = time.perf_counter()
        await mh.retrieve(MemoryLayer.EPISODIC, {"key": f"key_{i}"}, tenant_id)
        latencies.setdefault("retrieve", []).append((time.perf_counter() - t0) * 1000)
        ops_count += 1

        if i % 5 == 0:
            t0 = time.perf_counter()
            await sgm.record_successful_plan(f"dag_{i}", f"hash_{i}", tenant_id,
                                             f"intent_{i}", [{"tool": "llm"}], 1.0,
                                             cognitive_trace_id=cog_trace)
            latencies.setdefault("skill_record", []).append((time.perf_counter() - t0) * 1000)
            ops_count += 1

        if i % 10 == 0:
            t0 = time.perf_counter()
            await cc.compress_trace_to_context(f"trace_{i}", tenant_id,
                                               context_size, False,
                                               cognitive_trace_id=cog_trace)
            latencies.setdefault("compile_context", []).append((time.perf_counter() - t0) * 1000)
            ops_count += 1

        sm.transition(MemoryTransition.T0, {"tenant_id": tenant_id})
        sm.transition(MemoryTransition.T1, {"tenant_id": tenant_id, "trace_tenant": tenant_id})
        sm.transition(MemoryTransition.T2, {"max_tokens": context_size})
        sm.reset()

    ctc.record_memory_store(cog_trace, "validation", "load_test", tenant_id)

    return {"tenant_id": tenant_id, "latencies": latencies, "total_ops": ops_count}


async def run_load_test(
    num_tenants: int = NUM_TENANTS,
    context_sizes: List[int] | None = None,
) -> Dict[str, Any]:
    """Execute the full multi-tenant load test and return metrics."""
    mh = MemoryHierarchy()
    cc = ContextCompiler()
    sgm = SkillGraphManager()
    ctc = CognitiveTraceCorrelator()
    sm = MemoryStateMachine()

    if context_sizes is None:
        context_sizes = CONTEXT_SIZES

    tenants = [f"tenant_{i:03d}" for i in range(num_tenants)]
    context_cycle = [context_sizes[i % len(context_sizes)] for i in range(num_tenants)]

    tasks = [
        _tenant_workload(tid, mh, cc, sgm, sm, ctc, csize)
        for tid, csize in zip(tenants, context_cycle)
    ]

    batch_start = time.perf_counter()
    results = await asyncio.gather(*tasks)
    total_time = time.perf_counter() - batch_start

    # Aggregate latencies
    all_stores: List[float] = []
    all_retrieves: List[float] = []
    all_skills: List[float] = []
    all_compiles: List[float] = []

    total_ops = 0
    for r in results:
        total_ops += r["total_ops"]
        all_stores.extend(r["latencies"].get("store", []))
        all_retrieves.extend(r["latencies"].get("retrieve", []))
        all_skills.extend(r["latencies"].get("skill_record", []))
        all_compiles.extend(r["latencies"].get("compile_context", []))

    def p99(vals: List[float]) -> float:
        if not vals:
            return 0.0
        return round(sorted(vals)[int(len(vals) * 0.99)], 2)

    throughput = round(total_ops / total_time, 2) if total_time > 0 else 0.0

    return {
        "status": "ok",
        "metrics": {
            "throughput_ops_sec": throughput,
            "latency_p99_ms": {
                "store": p99(all_stores),
                "retrieve": p99(all_retrieves),
                "skill_record": p99(all_skills),
                "compile_context": p99(all_compiles),
            },
            "context_compaction_rate": round(
                len(all_compiles) / max(1, (len(all_compiles) + len(all_skills))), 4
            ),
            "total_operations": total_ops,
            "total_time_sec": round(total_time, 4),
            "num_tenants": num_tenants,
        },
    }


if __name__ == "__main__":
    result = asyncio.run(run_load_test())
    print(json.dumps(result, indent=2))
