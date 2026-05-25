"""Phase K3 — Usage Meter Implementation.  # LAW-1 LAW-11 LAW-12 LAW-23 LAW-24 RULE-1 RULE-2 RULE-3 RULE-4

Implements IUsageMeter protocol. Records billable operations per tenant,
aggregates daily usage, detects anomalies, and flushes to billing.

LAW 11: Meter state is instance-scoped — no global buffers.
LAW 12: Every record carries enterprise_trace_id.
LAW 23: Records are partitioned by tenant_id.
LAW 24: cost_units use Decimal for precision.
RULE 1: Same inputs yield identical record_hash (G-M1).

Ref: artifacts/design/j2/protocols/01_enterprise_protocols.py §IUsageMeter
Ref: EXEC-DIRECTIVE-024 §2 (Usage Metering & Billing)
"""

from __future__ import annotations

import datetime
import hashlib
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from core.enterprise.isolation_state_machine import IsolationStateMachine, RoutingTransition
from core.enterprise.trace_correlator import EnterpriseTraceCorrelator


RECORDED_OPERATION_TYPES = ("dag_execution", "api_call", "storage_gb")


class UsageMeter:  # LAW-1 LAW-11 LAW-12 LAW-23 LAW-24 RULE-1 RULE-2 RULE-3 RULE-4
    def __init__(
        self,
        trace_correlator: Optional[EnterpriseTraceCorrelator] = None,
        state_machine: Optional[IsolationStateMachine] = None,
        strict_enterprise_mode: bool = False,
        event_bus: Any = None,
    ) -> None:
        self._trace_correlator = trace_correlator or EnterpriseTraceCorrelator()
        self._state_machine = state_machine or IsolationStateMachine()
        self._strict_enterprise_mode = strict_enterprise_mode
        self._event_bus = event_bus
        self._buffers: Dict[str, List[Dict[str, Any]]] = {}

    def _publish_event(self, action: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent
            self._event_bus.publish(
                "enterprise.usage",
                ExecutionEvent(
                    event_id=f"entm_{int(time.time() * 1000000)}",
                    event_type="STATE_TRANSITION",
                    timestamp=time.time(),
                    source="UsageMeter",
                    payload={"action": action, **payload},
                ),
            )
        except Exception:
            pass

    async def record_operation(
        self,
        tenant_id: str,
        operation_type: str,
        cost_units: Decimal,
        enterprise_trace_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if tenant_id not in self._buffers:
            self._buffers[tenant_id] = []
        record_id = hashlib.sha256(
            f"{tenant_id}:{operation_type}:{cost_units}:{enterprise_trace_id}:{time.time_ns()}".encode()
        ).hexdigest()[:16]
        record_hash = hashlib.sha256(
            f"{tenant_id}:{operation_type}:{cost_units}:{enterprise_trace_id}".encode()
        ).hexdigest()[:32]
        record = {
            "record_id": record_id,
            "tenant_id": tenant_id,
            "operation_type": operation_type,
            "cost_units": cost_units,
            "timestamp_ns": time.time_ns(),
            "enterprise_trace_id": enterprise_trace_id,
            "hash": record_hash,
        }
        self._buffers[tenant_id].append(record)
        self._trace_correlator.record_trace(enterprise_trace_id, "usage_meter", record_id)
        self._publish_event("OperationRecorded", {
            "tenant_id": tenant_id, "operation_type": operation_type,
            "cost_units": str(cost_units), "enterprise_trace_id": enterprise_trace_id,
        })
        return {
            "record_id": record_id,
            "hash": record_hash,
            "buffered": True,
            "trace_id": enterprise_trace_id,
        }

    async def accumulate_usage_by_type(self, tenant_id: str) -> Dict[str, Decimal]:
        records = self._buffers.get(tenant_id, [])
        totals: Dict[str, Decimal] = {}
        for r in records:
            t = r["operation_type"]
            totals[t] = totals.get(t, Decimal("0")) + r["cost_units"]
        return totals

    async def aggregate_daily_usage(
        self,
        tenant_id: str,
        date: datetime.date,
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        records = self._buffers.get(tenant_id, [])
        totals: Dict[str, Decimal] = {}
        total_units = Decimal("0")
        for r in records:
            t = r["operation_type"]
            totals[t] = totals.get(t, Decimal("0")) + r["cost_units"]
            total_units += r["cost_units"]
        return {
            "tenant_id": tenant_id,
            "date": str(date),
            "totals": totals,
            "total_units": total_units,
            "record_count": len(records),
            "trace_id": enterprise_trace_id,
        }

    async def detect_anomalies(
        self,
        tenant_id: str,
        usage_snapshot: Dict[str, Any],
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        total_cost = usage_snapshot.get("total_cost", Decimal("0"))
        if isinstance(total_cost, str):
            total_cost = Decimal(total_cost)
        daily_avg = Decimal("1000")
        threshold = daily_avg * Decimal("2")
        anomalous = total_cost > threshold
        anomaly_score = float(total_cost / daily_avg) if daily_avg > 0 else 0.0
        flagged_ops: List[str] = []
        detail_parts: List[str] = []
        for op_type, units in usage_snapshot.get("totals", {}).items():
            if isinstance(units, Decimal) and units > Decimal("50000"):
                flagged_ops.append(str(op_type))
                detail_parts.append(f"{op_type}={units}")
        if anomalous:
            detail_parts.append(f"total_cost={total_cost}>threshold={threshold}")
        return {
            "anomalous": anomalous,
            "anomaly_score": round(anomaly_score, 4),
            "flagged_ops": flagged_ops,
            "detail": "; ".join(detail_parts) if detail_parts else "No anomalies detected",
            "trace_id": enterprise_trace_id,
        }

    async def flush_to_billing(
        self,
        tenant_id: str,
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        records = self._buffers.pop(tenant_id, [])
        total_cost = sum(r["cost_units"] for r in records) if records else Decimal("0")
        return {
            "flushed": len(records),
            "total_cost": total_cost,
            "billing_trace": enterprise_trace_id,
        }

    def get_buffer_size(self, tenant_id: str) -> int:
        return len(self._buffers.get(tenant_id, []))
