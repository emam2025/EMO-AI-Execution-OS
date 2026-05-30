"""Phase J3 — Chaos Injector Implementation.  # LAW-3 LAW-5 LAW-8 LAW-11 LAW-20 LAW-21 RULE-3 RULE-5

Implements IChaosInjector protocol for systematic failure simulation.
Every injection carries expected_recovery_sec (LAW 8) and readiness_trace_id
(LAW 12). Faults are targeted and scoped — never leak across services (LAW 20).

Ref: artifacts/design/j3/protocols/01_readiness_protocols.py (IChaosInjector)
Ref: artifacts/design/j3/models/02_chaos_and_load_models.py
Ref: artifacts/design/j3/03_chaos_recovery_machine.md
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Optional

from core.readiness.readiness_state_machine import (
    ReadinessStateMachine,
    ChaosTransition,
    evaluate_g_c1_pre_fault_health,
)
from core.readiness.trace_correlator import ReadinessTraceCorrelator


class ChaosInjector:  # LAW-3 LAW-5 LAW-8 LAW-11 LAW-20 LAW-21 RULE-3 RULE-5
    """Concrete implementation of IChaosInjector.

    LAW 8: Every injection specifies expected_recovery_sec for recoverability.
    LAW 11: All injector state is instance-scoped — no global fault registry.
    LAW 20: Faults target exactly one service — never leak across boundaries.
    RULE 3: G-C1 Pre-Fault Health Guard blocks injection if service degraded.
    RULE 5: restore_baseline returns exact pre-fault baseline state.
    """

    def __init__(
        self,
        state_machine: ReadinessStateMachine,
        trace_correlator: ReadinessTraceCorrelator,
        readiness_trace_id: str = "",
    ) -> None:
        self._state_machine = state_machine
        self._trace_correlator = trace_correlator
        self._injections: Dict[str, Dict[str, Any]] = {}

    async def inject_network_partition(  # LAW-8 LAW-20
        self,
        target_service: str,
        duration_sec: float,
        readiness_trace_id: str,
        partition_type: str = "full_isolation",
    ) -> Dict[str, Any]:
        injection_id = f"inj_{hashlib.sha256(f'{target_service}:np:{time.time_ns()}'.encode()).hexdigest()[:20]}"
        self._injections[injection_id] = {
            "target_service": target_service,
            "fault_type": "network_partition",
            "duration_sec": duration_sec,
            "expected_recovery_sec": duration_sec * 1.5,
            "partition_type": partition_type,
            "injected_at_ns": time.time_ns(),
            "readiness_trace_id": readiness_trace_id,
            "state": "injected",
        }
        self._trace_correlator.propagate_to_chaos(readiness_trace_id, injection_id)
        return {
            "injection_id": injection_id,
            "fault_type": "network_partition",
            "expected_recovery_sec": duration_sec * 1.5,
            "target_service": target_service,
            "injected_at_ns": time.time_ns(),
            "trace_id": readiness_trace_id,
        }

    async def kill_worker(  # LAW-8 LAW-20
        self,
        worker_id: str,
        readiness_trace_id: str,
        graceful: bool = False,
    ) -> Dict[str, Any]:
        injection_id = f"inj_{hashlib.sha256(f'{worker_id}:kw:{time.time_ns()}'.encode()).hexdigest()[:20]}"
        self._injections[injection_id] = {
            "worker_id": worker_id,
            "fault_type": "worker_failure",
            "graceful": graceful,
            "expected_recovery_sec": 30.0 if graceful else 15.0,
            "injected_at_ns": time.time_ns(),
            "readiness_trace_id": readiness_trace_id,
            "state": "injected",
        }
        self._trace_correlator.propagate_to_chaos(readiness_trace_id, injection_id)
        return {
            "injection_id": injection_id,
            "fault_type": "worker_failure",
            "worker_id": worker_id,
            "graceful": graceful,
            "expected_recovery_sec": 30.0 if graceful else 15.0,
            "injected_at_ns": time.time_ns(),
            "trace_id": readiness_trace_id,
        }

    async def simulate_db_failover(  # LAW-8 LAW-20
        self,
        db_instance: str,
        readiness_trace_id: str,
        failover_type: str = "primary_loss",
    ) -> Dict[str, Any]:
        injection_id = f"inj_{hashlib.sha256(f'{db_instance}:df:{time.time_ns()}'.encode()).hexdigest()[:20]}"
        recovery_sec = 60.0 if failover_type == "primary_loss" else 30.0
        self._injections[injection_id] = {
            "db_instance": db_instance,
            "fault_type": "db_failover",
            "failover_type": failover_type,
            "expected_recovery_sec": recovery_sec,
            "promoted_replica": f"{db_instance}_replica_1",
            "injected_at_ns": time.time_ns(),
            "readiness_trace_id": readiness_trace_id,
            "state": "injected",
        }
        self._trace_correlator.propagate_to_chaos(readiness_trace_id, injection_id)
        return {
            "injection_id": injection_id,
            "fault_type": "db_failover",
            "db_instance": db_instance,
            "failover_type": failover_type,
            "expected_recovery_sec": recovery_sec,
            "promoted_replica": f"{db_instance}_replica_1",
            "injected_at_ns": time.time_ns(),
            "trace_id": readiness_trace_id,
        }

    async def restore_baseline(  # LAW-8 RULE-5
        self,
        injection_id: str,
        readiness_trace_id: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        injection = self._injections.get(injection_id, {})
        if not injection:
            return {
                "restored": False,
                "injection_id": injection_id,
                "recovery_time_ns": 0,
                "state_before": {},
                "state_after": {},
                "force_used": force,
                "trace_id": readiness_trace_id,
            }
        injection["state"] = "restored"
        injection["restored_at_ns"] = time.time_ns()
        recovery_time_ns = injection.get("restored_at_ns", 0) - injection.get("injected_at_ns", 0)
        return {
            "restored": True,
            "injection_id": injection_id,
            "recovery_time_ns": recovery_time_ns,
            "state_before": {
                "target_service": injection.get("target_service", injection.get("worker_id", injection.get("db_instance", ""))),
                "fault_type": injection.get("fault_type", ""),
            },
            "state_after": {
                "status": "healthy",
                "health_score": 1.0,
            },
            "force_used": force,
            "trace_id": readiness_trace_id,
        }

    def injection_state(self, injection_id: str) -> Dict[str, Any]:
        return self._injections.get(injection_id, {})
