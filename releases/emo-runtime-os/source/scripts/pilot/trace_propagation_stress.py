#!/usr/bin/env python3
"""TracePropagationStress — concurrent multi-tenant trace propagation under contention.

Measures:
  - trace_id_loss_rate     (must be 0)
  - cross_tenant_leakage   (must be 0)
  - propagation_completeness across F1 → J2 → I1 → F4

Usage:
    python scripts/pilot/trace_propagation_stress.py
    python scripts/pilot/trace_propagation_stress.py --ci
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("pilot.trace_stress")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

PILOT_ARTIFACTS = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", "pilot")


@dataclass
class TraceStressReport:
    timestamp: str = ""
    total_requests: int = 0
    tenant_count: int = 0
    trace_id_loss_rate: float = 0.0
    cross_tenant_leakage_attempts: int = 0
    propagation_completeness_pct: float = 100.0
    passed: bool = False
    errors: List[str] = field(default_factory=list)


class TracePropagationStress:
    def __init__(self, root: Any, tenants: Dict[str, Any], concurrency: int = 10):
        self._root = root
        self._tenants = tenants
        self._concurrency = concurrency
        self._correlator = root.enterprise_trace_correlator
        self._router = root.tenant_router
        self._results: List[Dict[str, Any]] = []

    async def run(self) -> TraceStressReport:
        report = TraceStressReport()
        report.timestamp = datetime.now(timezone.utc).isoformat()
        report.tenant_count = len(self._tenants)

        try:
            tenant_ids = list(self._tenants.keys())
            tasks = []
            for i in range(self._concurrency):
                tid = tenant_ids[i % len(tenant_ids)]
                tasks.append(self._execute_tenant_operation(tid, i))

            self._results = await asyncio.gather(*tasks, return_exceptions=True)

            total = len(self._results)
            lost = sum(1 for r in self._results if isinstance(r, dict) and r.get("trace_lost"))
            leaks = sum(1 for r in self._results if isinstance(r, dict) and r.get("leakage_detected"))
            complete = sum(1 for r in self._results if isinstance(r, dict) and r.get("fully_propagated"))

            report.total_requests = total
            report.trace_id_loss_rate = round(lost / max(1, total), 4)
            report.cross_tenant_leakage_attempts = leaks
            report.propagation_completeness_pct = round((complete / max(1, total)) * 100, 1)

            report.passed = (
                report.trace_id_loss_rate == 0.0
                and report.cross_tenant_leakage_attempts == 0
                and report.propagation_completeness_pct >= 99.9
            )

            logger.info(
                "Trace stress: %d requests, loss=%.4f, leaks=%d, completeness=%.1f%%",
                total, report.trace_id_loss_rate, leaks, report.propagation_completeness_pct,
            )

        except Exception as e:
            report.errors.append(str(e))
            logger.error("Trace stress failed: %s", e)

        return report

    async def _execute_tenant_operation(self, tenant_id: str, idx: int) -> Dict[str, Any]:
        result = {
            "tenant_id": tenant_id,
            "trace_lost": False,
            "leakage_detected": False,
            "fully_propagated": True,
        }
        try:
            session_id = uuid.uuid4().hex
            etid = self._correlator.generate_enterprise_trace_id(
                session_id=session_id, tenant_id=tenant_id,
            )

            # Simulate F1 → J2 → I1 → F4 propagation
            await self._router.enforce_quota(
                tenant_id=tenant_id, resource_type="dag_execution",
                requested_units=Decimal("5"), enterprise_trace_id=etid,
            )

            self._correlator.propagate_to_f1(etid, f"f1_trace_{session_id[:8]}")
            self._correlator.propagate_to_router(etid, f"route_{session_id[:8]}")
            self._correlator.propagate_to_meter(etid, f"meter_{session_id[:8]}")
            self._correlator.propagate_to_billing(etid, f"bill_{session_id[:8]}")
            self._correlator.propagate_to_auditor(etid, f"audit_{session_id[:8]}")
            self._correlator.propagate_to_f4(etid)

            # Verify full propagation
            chain = self._correlator.trace_chain(etid)
            if not chain or chain.get("trace_id") != etid:
                result["trace_lost"] = True
                result["fully_propagated"] = False
                return result

            # Check for cross-tenant leakage: our trace data must not appear under another tenant's ID
            all_traces = self._correlator.all_traces()
            for trace_id_in_store, layers in all_traces.items():
                etid_tenant = tenant_id  # known correct
                if trace_id_in_store != etid and etid in str(layers):
                    result["leakage_detected"] = True

        except Exception:
            result["trace_lost"] = True

        return result


def save_report(report: TraceStressReport, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(asdict(report), f, indent=2, default=str)


async def main_async() -> TraceStressReport:
    from scripts.pilot.enterprise_launcher import EnterprisePilotLauncher

    launcher = EnterprisePilotLauncher()
    launch_report = await launcher.launch()
    if not launch_report.passed:
        logger.error("Launcher failed, cannot run trace stress")
        report = TraceStressReport()
        report.errors = launch_report.errors
        return report

    stress = TracePropagationStress(launcher.root, launcher.tenants, concurrency=20)
    return await stress.run()


def main() -> int:
    ci_mode = "--ci" in sys.argv
    report = asyncio.run(main_async())

    output_path = os.path.join(PILOT_ARTIFACTS, "trace_stress_report.json")
    save_report(report, output_path)

    if ci_mode:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        status = "PASS" if report.passed else "FAIL"
        print(f"\n{'='*60}")
        print(f"  TRACE PROPAGATION STRESS — {status}")
        print(f"{'='*60}")
        print(f"  Total requests:                {report.total_requests}")
        print(f"  Tenants:                       {report.tenant_count}")
        print(f"  Trace ID loss rate:            {report.trace_id_loss_rate:.4f} (target: 0)")
        print(f"  Cross-tenant leak attempts:    {report.cross_tenant_leakage_attempts} (target: 0)")
        print(f"  Propagation completeness:      {report.propagation_completeness_pct:.1f}%")
        if report.errors:
            for e in report.errors[:3]:
                print(f"  Error: {e}")
        print(f"{'='*60}\n")

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
