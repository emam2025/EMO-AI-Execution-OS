"""AuditWiring — checks CompositionRoot for concrete implementations, no None fallbacks."""

# LAW-5: Observable — all wiring check results published via EventBus
# LAW-8: Traceable — every audit step carries audit_trace_id
# LAW-11: No Global State — audit state is instance-scoped
# RULE-3: Guards enforce preconditions — None fallback detection

from __future__ import annotations

import dataclasses
import hashlib
import time
from typing import Any, Dict, List, Optional, Protocol


@dataclasses.dataclass(frozen=True)
class WiringCheckResult:
    protocol_name: str
    concrete_type: Optional[str]
    is_wired: bool
    is_none_fallback: bool
    detail: str


@dataclasses.dataclass(frozen=True)
class AuditWiringReport:
    timestamp_ns: int
    audit_trace_id: str
    total_protocols: int
    wired_protocols: int
    none_fallbacks: int
    unused_protocols: int
    checks: List[WiringCheckResult]
    passed: bool
    summary: str


class IAuditWiring(Protocol):
    def audit_composition_root(self, root: Any) -> AuditWiringReport:
        ...


class AuditWiring:
    def __init__(self, event_bus: Any = None):
        raw = f"audit_wiring_{time.time_ns()}"
        self._trace_id = "aw_" + hashlib.sha256(raw.encode()).hexdigest()[:28]
        self._event_bus = event_bus
        self._protocol_map: Dict[str, List[str]] = {
            "IEventBus": ["_event_bus"],
            "ICheckpointManager": ["_checkpoint_manager"],
            "IContractValidator": ["_contract_validator"],
            "IComplianceValidator": ["_compliance_validator"],
            "ICostTracker": ["_cost_tracker"],
            "IDAGOptimizer": ["_optimizer"],
            "IExecutionEngine": ["_engine"],
            "IDAGSizeLimiter": ["_size_limiter"],
            "ISystemAuditor": ["_system_auditor"],
            "ILoadGenerator": ["_load_generator"],
            "ISecurityValidator": ["_security_validator"],
            "ICertificationEngine": ["_certification_engine"],
            "ITenantRouter": ["_tenant_router"],
            "IUsageMeter": ["_usage_meter"],
            "IBillingEngine": ["_billing_engine"],
            "IComplianceAuditor": ["_compliance_auditor"],
            "IChaosInjector": ["_chaos_injector"],
            "ILoadOrchestrator": ["_load_orchestrator"],
            "IStabilityValidator": ["_stability_validator"],
            "ICertificationGate": ["_certification_gate"],
            "ICanaryObserver": ["_canary_observer"],
            "ISDKClient": ["_sdk_client"],
            "ICLIRuntime": ["_cli_runtime"],
            "IDocGenerator": ["_doc_generator"],
            "IAPISpecPublisher": ["_api_spec_publisher"],
            "IFailoverOrchestrator": ["_failover_orchestrator"],
            "IDisasterRecovery": ["_disaster_recovery"],
            "IRollingUpdateManager": ["_rolling_update_manager"],
            "IRuntimeMigrator": ["_runtime_migrator"],
        }

    @property
    def audit_trace_id(self) -> str:
        return self._trace_id

    def audit_composition_root(self, root: Any) -> AuditWiringReport:
        checks: List[WiringCheckResult] = []
        none_fallbacks = 0
        wired = 0

        for protocol_name, attr_names in self._protocol_map.items():
            concrete_type = None
            is_wired = False
            is_none = True
            for attr in attr_names:
                val = getattr(root, attr, None) if hasattr(root, attr) else None
                if val is not None:
                    is_wired = True
                    is_none = False
                    concrete_type = type(val).__name__
                    break

            if is_none:
                none_fallbacks += 1

            checks.append(WiringCheckResult(
                protocol_name=protocol_name,
                concrete_type=concrete_type,
                is_wired=is_wired,
                is_none_fallback=is_none,
                detail=(
                    f"Concrete: {concrete_type}" if is_wired
                    else "NONE FALLBACK — not wired"
                ),
            ))
            if is_wired:
                wired += 1

        passed = none_fallbacks == 0
        report = AuditWiringReport(
            timestamp_ns=time.time_ns(),
            audit_trace_id=self._trace_id,
            total_protocols=len(checks),
            wired_protocols=wired,
            none_fallbacks=none_fallbacks,
            unused_protocols=0,
            checks=checks,
            passed=passed,
            summary=(
                "ALL PROTOCOLS WIRED — 0 none fallbacks"
                if passed
                else f"{none_fallbacks} NONE FALLBACKS DETECTED — audit failed"
            ),
        )

        if self._event_bus is not None:
            self._publish(report)
        return report

    def _publish(self, report: AuditWiringReport) -> None:
        try:
            from core.models.events import ExecutionEvent, EventType
            event = ExecutionEvent(
                event_id=self._trace_id[:16],
                event_type=EventType.STATE_TRANSITION,
                timestamp_ns=report.timestamp_ns,
                payload={
                    "action": "audit_wiring_complete",
                    "audit_trace_id": self._trace_id,
                    "passed": report.passed,
                    "total": report.total_protocols,
                    "wired": report.wired_protocols,
                    "none_fallbacks": report.none_fallbacks,
                },
            )
            self._event_bus.publish("runtime.audit.wiring", event)
        except Exception:
            pass
