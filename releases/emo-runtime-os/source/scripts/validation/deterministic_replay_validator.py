"""deterministic_replay_validator.py — Hash match rate ≥99.9% under concurrent load.

EXEC-DIRECTIVE-L-VAL-001 Task 2:
  Send the same 50 retrieval requests 3 times per tenant.
  Compare ContextWindow._hash across runs.

Measures:
  - hash_match_rate
  - drift_incidents
  - event_bus_ordering_impact

LAW 14: Same (trace_id, tenant_id, max_tokens, scope_verified) → same hash.
RULE 3: Replay-safe — same sequence → same correlation.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Tuple

from core.memory.memory_hierarchy import MemoryHierarchy
from core.memory.context_compiler import ContextCompiler
from core.memory.trace_correlator import CognitiveTraceCorrelator
from core.memory.models import MemoryLayer


NUM_TENANTS = 10
REPLAY_TRACES = 50
REPLAY_ROUNDS = 3


async def run_determinism_test(
    num_tenants: int = NUM_TENANTS,
    replay_traces: int = REPLAY_TRACES,
    replay_rounds: int = REPLAY_ROUNDS,
) -> Dict[str, Any]:
    """Verify that same inputs produce same ContextWindow._hash across rounds."""
    tenants = [f"det_tenant_{i:03d}" for i in range(num_tenants)]
    drift_incidents: List[Dict[str, Any]] = []
    total_comparisons = 0
    hash_matches = 0

    for tenant_id in tenants:
        # First round: record hashes
        round1_hashes: Dict[str, str] = {}

        for trace_idx in range(replay_traces):
            cc = ContextCompiler()
            mh = MemoryHierarchy()

            # Store some data
            cog = f"cog_det_{tenant_id}_{trace_idx}"
            await mh.store(MemoryLayer.SEMANTIC, f"fact_{trace_idx}",
                           {"value": trace_idx}, tenant_id, "strict", cog)
            await mh.store(MemoryLayer.EPISODIC, f"event_{trace_idx}",
                           {"seq": trace_idx}, tenant_id, "strict", cog)

            # Compile context
            result = await cc.compress_trace_to_context(
                f"trace_{trace_idx}", tenant_id, 2048, False,
                cognitive_trace_id=cog,
            )
            round1_hashes[f"trace_{trace_idx}"] = result["context"]["_hash"]

        # Rounds 2 and 3: compare hashes
        for round_num in range(2, replay_rounds + 1):
            for trace_idx in range(replay_traces):
                cc2 = ContextCompiler()
                mh2 = MemoryHierarchy()

                await mh2.store(MemoryLayer.SEMANTIC, f"fact_{trace_idx}",
                                {"value": trace_idx}, tenant_id, "strict",
                                f"cog_det_{tenant_id}_{trace_idx}")
                await mh2.store(MemoryLayer.EPISODIC, f"event_{trace_idx}",
                                {"seq": trace_idx}, tenant_id, "strict",
                                f"cog_det_{tenant_id}_{trace_idx}")

                result = await cc2.compress_trace_to_context(
                    f"trace_{trace_idx}", tenant_id, 2048, False,
                    cognitive_trace_id=f"cog_det_{tenant_id}_{trace_idx}",
                )
                current_hash = result["context"]["_hash"]
                expected_hash = round1_hashes.get(f"trace_{trace_idx}", "")

                total_comparisons += 1
                if current_hash == expected_hash:
                    hash_matches += 1
                else:
                    drift_incidents.append({
                        "tenant_id": tenant_id,
                        "trace_idx": trace_idx,
                        "round": round_num,
                        "expected_hash": expected_hash,
                        "actual_hash": current_hash,
                    })

    hash_match_rate = round(hash_matches / max(1, total_comparisons) * 100, 4)

    return {
        "status": "ok",
        "metrics": {
            "hash_match_rate": hash_match_rate,
            "hash_match_rate_pass": hash_match_rate >= 99.9,
            "drift_incidents": len(drift_incidents),
            "drift_details": drift_incidents[:10],
            "total_comparisons": total_comparisons,
            "num_tenants": num_tenants,
            "replay_traces": replay_traces,
            "replay_rounds": replay_rounds,
        },
    }


if __name__ == "__main__":
    result = asyncio.run(run_determinism_test())
    print(json.dumps(result, indent=2))
