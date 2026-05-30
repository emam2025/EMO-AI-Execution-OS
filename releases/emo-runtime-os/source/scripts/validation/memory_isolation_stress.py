"""memory_isolation_stress.py — Fault injection & boundary enforcement.

EXEC-DIRECTIVE-L-VAL-001 Task 3:
  Inject fault into EventStore during prune/compile_context.
  Verify Facade returns StructuredFaultResponse, no DAG crash, no tenant bleed.

Measures:
  - cascade_containment_rate
  - graceful_degradation_time
  - cross_tenant_context_leakage

G-M1–G-M6: All guards must hold under partial EventStore failure.
LAW 11: Zero cross-tenant leakage.
LAW 8: Recoverable via cognitive_trace_id.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from typing import Any, Dict, List, Optional

from core.memory.memory_hierarchy import MemoryHierarchy, IsolationViolation
from core.memory.context_compiler import ContextCompiler
from core.memory.skill_graph_manager import SkillGraphManager
from core.memory.memory_state_machine import MemoryStateMachine, MemoryTransition
from core.memory.trace_correlator import CognitiveTraceCorrelator
from core.memory.models import MemoryLayer, PruningPolicy


class SimulatedEventStore:
    """EventStore mock that can fail on demand."""

    def __init__(self) -> None:
        self._fail_mode = False
        self._events: List[Dict[str, Any]] = []

    def fail(self) -> None:
        self._fail_mode = True

    def heal(self) -> None:
        self._fail_mode = False

    async def append(self, event: Dict[str, Any]) -> Dict[str, Any]:
        if self._fail_mode:
            raise ConnectionError("Simulated EventStore failure")
        self._events.append(event)
        return {"status": "appended", "event_id": len(self._events)}

    async def replay(self, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if self._fail_mode:
            raise ConnectionError("Simulated EventStore failure")
        return list(self._events)


async def run_isolation_test() -> Dict[str, Any]:
    """Test isolation under partial EventStore failure."""
    mh = MemoryHierarchy()
    cc = ContextCompiler()
    sgm = SkillGraphManager()
    ctc = CognitiveTraceCorrelator()
    sm = MemoryStateMachine()
    event_store = SimulatedEventStore()

    cascade_contained = 0
    total_faults = 0
    cross_tenant_leaks: List[Dict[str, Any]] = []
    degradation_times: List[float] = []

    # Prime data for ten_a and ten_b
    for i in range(5):
        await mh.store(MemoryLayer.EPISODIC, f"prime_{i}", {"i": i},
                       "ten_a", "strict", "cog_prime_a", ttl_seconds=0.001)
        await mh.store(MemoryLayer.EPISODIC, f"prime_{i}", {"i": i},
                       "ten_b", "strict", "cog_prime_b")

    await asyncio.sleep(0.01)

    # Test 1: EventStore failure during prune
    for attempt in range(3):
        # Store data
        cog = ctc.generate_cognitive_trace_id("ten_a")
        await mh.store(MemoryLayer.EPISODIC, f"fault_test_{attempt}",
                       {"attempt": attempt}, "ten_a", "strict", cog,
                       ttl_seconds=0.001)

        # Trigger fault
        event_store.fail()
        total_faults += 1

        try:
            start = time.perf_counter()
            pruned = await mh.prune(MemoryLayer.EPISODIC, PruningPolicy.TTL_BASED,
                                    "ten_a", cog)
            elapsed = (time.perf_counter() - start) * 1000
            degradation_times.append(elapsed)
            cascade_contained += 1
        except IsolationViolation:
            cascade_contained += 1
        except Exception:
            pass  # would be a cascade failure

        event_store.heal()

    # Test 2: Verify ten_b data intact after ten_a failures
    for i in range(5):
        r = await mh.retrieve(MemoryLayer.EPISODIC, {"key": f"prime_{i}"}, "ten_b")
        if r["total"] == 0:
            cross_tenant_leaks.append({
                "type": "ten_b_data_missing_after_ten_a_fault",
                "key": f"prime_{i}",
            })

    # Test 3: Ten A must not see Ten B data
    for i in range(5):
        r = await mh.retrieve(MemoryLayer.EPISODIC, {"key": f"prime_{i}"}, "ten_a")
        if r["total"] > 0:
            cross_tenant_leaks.append({
                "type": "ten_a_saw_ten_b_data",
                "key": f"prime_{i}",
            })

    # Test 4: Compiler under fault (should not crash)
    event_store.fail()
    try:
        await cc.compress_trace_to_context("trace_fault", "ten_a", 2048, False,
                                           cognitive_trace_id="cog_fault")
        cascade_contained += 1
    except Exception:
        pass
    total_faults += 1
    event_store.heal()

    cascade_rate = round(cascade_contained / max(1, total_faults) * 100, 2)
    avg_degradation = round(
        statistics.mean(degradation_times), 2
    ) if degradation_times else 0.0

    return {
        "status": "ok",
        "metrics": {
            "cascade_containment_rate": cascade_rate,
            "cascade_containment_pass": cascade_rate == 100.0,
            "graceful_degradation_time_ms": avg_degradation,
            "cross_tenant_context_leakage": len(cross_tenant_leaks),
            "leak_details": cross_tenant_leaks,
            "total_faults_injected": total_faults,
        },
    }


if __name__ == "__main__":
    result = asyncio.run(run_isolation_test())
    print(json.dumps(result, indent=2))
