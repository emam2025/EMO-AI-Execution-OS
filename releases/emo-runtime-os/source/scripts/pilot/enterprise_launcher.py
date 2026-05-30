#!/usr/bin/env python3
"""EnterprisePilotLauncher — activate strict enterprise mode with multi-tenant isolation.

LAW 11, 12, 23-27: Tenant isolation, quota enforcement, billing determinism,
compliance audit, trace propagation under contention.

Usage:
    python scripts/pilot/enterprise_launcher.py
    python scripts/pilot/enterprise_launcher.py --ci   # JSON output
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
logger = logging.getLogger("pilot.enterprise_launcher")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

TENANTS = [
    {"id": "tenant-alpha",  "tier": "starter",     "quotas": {"dag_execution": "1000", "api_call": "5000",  "storage_gb": "50"},   "workers": 2},
    {"id": "tenant-beta",   "tier": "professional", "quotas": {"dag_execution": "5000", "api_call": "20000", "storage_gb": "200"},  "workers": 4},
    {"id": "tenant-gamma",  "tier": "enterprise",   "quotas": {"dag_execution": "20000","api_call": "100000","storage_gb": "1000"}, "workers": 8},
    {"id": "tenant-delta",  "tier": "starter",      "quotas": {"dag_execution": "500",  "api_call": "2500",  "storage_gb": "25"},   "workers": 2},
    {"id": "tenant-epsilon","tier": "professional", "quotas": {"dag_execution": "3000", "api_call": "15000", "storage_gb": "150"},  "workers": 4},
    {"id": "tenant-zeta",   "tier": "enterprise",   "quotas": {"dag_execution": "15000","api_call": "75000", "storage_gb": "750"},  "workers": 6},
    {"id": "tenant-eta",    "tier": "starter",      "quotas": {"dag_execution": "750",  "api_call": "4000",  "storage_gb": "40"},   "workers": 2},
    {"id": "tenant-theta",  "tier": "professional", "quotas": {"dag_execution": "4000", "api_call": "18000", "storage_gb": "180"},  "workers": 4},
    {"id": "tenant-iota",   "tier": "enterprise",   "quotas": {"dag_execution": "25000","api_call": "120000","storage_gb": "1200"}, "workers": 8},
    {"id": "tenant-kappa",  "tier": "starter",      "quotas": {"dag_execution": "600",  "api_call": "3000",  "storage_gb": "30"},   "workers": 2},
]

PILOT_ARTIFACTS = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", "pilot")


@dataclass
class TenantRegistrationResult:
    tenant_id: str
    tier: str
    isolated_repo_path: str
    dedicated_worker_pool_size: int
    quota_limits: Dict[str, str]
    registered: bool


@dataclass
class LaunchReport:
    timestamp: str = ""
    strict_enterprise_mode: bool = True
    tenant_count: int = 0
    tenants: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    passed: bool = False


class EnterprisePilotLauncher:
    def __init__(self):
        self._root: Any = None
        self._tenants: Dict[str, Any] = {}
        self._trace_correlator: Any = None
        self._start_time: float = 0.0

    async def launch(self) -> LaunchReport:
        report = LaunchReport()
        report.timestamp = datetime.now(timezone.utc).isoformat()
        self._start_time = time.time()

        try:
            from core.composition.root import CompositionRoot
            from core.runtime.event_bus import InMemoryEventBus
            from core.runtime.event_store import EventStore

            event_bus = InMemoryEventBus()
            event_store = EventStore(
                path=os.path.join(PILOT_ARTIFACTS, "pilot_events.jsonl")
            )

            self._root = CompositionRoot(
                event_bus=event_bus,
                event_store=event_store,
                strict_enterprise_mode=True,
            )

            tenant_root_path = os.path.join(PILOT_ARTIFACTS, "tenants")
            os.makedirs(tenant_root_path, exist_ok=True)

            for t in TENANTS:
                tid = t["id"]
                isolated_repo = os.path.join(tenant_root_path, tid)
                os.makedirs(isolated_repo, exist_ok=True)

                quotas_decimal = {
                    k: Decimal(v) for k, v in t["quotas"].items()
                }

                self._root.tenant_router.register_tenant(
                    tenant_id=tid,
                    isolation_policy="strict",
                    quotas=quotas_decimal,
                )

                self._tenants[tid] = {
                    "tier": t["tier"],
                    "isolated_repo_path": isolated_repo,
                    "dedicated_worker_pool_size": t["workers"],
                    "quota_limits": t["quotas"],
                }
                report.tenants.append({
                    "tenant_id": tid,
                    "tier": t["tier"],
                    "isolated_repo_path": isolated_repo,
                    "dedicated_worker_pool_size": t["workers"],
                    "quota_limits": t["quotas"],
                })

            self._trace_correlator = self._root.enterprise_trace_correlator

            report.tenant_count = len(self._tenants)
            report.passed = True
            logger.info(
                "EnterprisePilotLauncher: %d tenants registered, strict_enterprise_mode=True",
                report.tenant_count,
            )

        except Exception as e:
            report.errors.append(str(e))
            logger.error("Launch failed: %s", e)

        return report

    @property
    def root(self) -> Any:
        return self._root

    @property
    def trace_correlator(self) -> Any:
        return self._trace_correlator

    @property
    def tenants(self) -> Dict[str, Any]:
        return self._tenants


def save_report(report: LaunchReport, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(asdict(report), f, indent=2, default=str)


def main() -> int:
    ci_mode = "--ci" in sys.argv

    launcher = EnterprisePilotLauncher()
    report = asyncio.run(launcher.launch())

    output_path = os.path.join(PILOT_ARTIFACTS, "enterprise_launch_report.json")
    save_report(report, output_path)

    if ci_mode:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        status = "PASS" if report.passed else "FAIL"
        print(f"\n{'='*60}")
        print(f"  ENTERPRISE PILOT LAUNCH — {status}")
        print(f"{'='*60}")
        print(f"  strict_enterprise_mode: {report.strict_enterprise_mode}")
        print(f"  Tenants registered:     {report.tenant_count}")
        for t in report.tenants:
            print(f"    {t['tenant_id']:20s} tier={t['tier']:15s} workers={t['dedicated_worker_pool_size']}")
        if report.errors:
            for e in report.errors[:5]:
                print(f"  Error: {e}")
        print(f"{'='*60}\n")

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
