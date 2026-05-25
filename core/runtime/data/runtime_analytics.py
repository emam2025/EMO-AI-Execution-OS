"""Phase I2 — Runtime Analytics Implementation.  # LAW-5 LAW-15 LAW-16 RULE-1 RULE-2 RULE-3

Implements IRuntimeAnalytics protocol with throughput computation, anomaly
detection, metric aggregation, and dashboard publishing.

Ref: Canon LAW 5 (Observability), LAW 15 (Cost Budgets)
Ref: Canon LAW 16 (Worker Fairness)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO), RULE 3 (Safety)
Ref: artifacts/design/i2/protocols/01_data_infra_protocols.py
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from core.interfaces.event_bus import IEventBus
from core.runtime.event_bus import InMemoryEventBus
from core.models.events import ExecutionEvent


class RuntimeAnalytics:  # LAW-5 LAW-15 LAW-16 RULE-1 RULE-2 RULE-3
    """Deterministic analytics engine for throughput, anomalies, and dashboards.

    All computations are deterministic (RULE 1) and respect cost budgets
    (LAW 15) and worker fairness (LAW 16).
    """

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus or InMemoryEventBus()
        self._windows: Dict[str, Dict[str, Any]] = {}
        self._dashboards: Dict[str, Dict[str, Any]] = {}

    def _publish_event(self, action: str, resource: str, data_trace_id: str, **extra: Any) -> None:
        event = ExecutionEvent(
            event_id=uuid.uuid4().hex[:16],
            event_type=f"ANALYTICS_{action.upper()}",
            source="RuntimeAnalytics",
            payload={"resource": resource, "data_trace_id": data_trace_id, **extra},
            timestamp=time.time(),
        )
        self._event_bus.publish("runtime.data.analytics", event)

    def compute_throughput(  # LAW-15 RULE-1
        self,
        window_id: str,
        metrics: List[Dict[str, Any]],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        if not metrics:
            return {"window_id": window_id, "operations_per_sec": 0.0,
                    "avg_latency_ms": 0.0, "p99_latency_ms": 0.0,
                    "total_operations": 0, "cost_estimate": 0.0}

        total_ops = len(metrics)
        latencies = [m.get("value", 0.0) for m in metrics if "value" in m]
        timestamps = [m.get("timestamp", 0) for m in metrics if "timestamp" in m]

        time_span_sec = 1.0
        if len(timestamps) >= 2:
            time_span_sec = max(1.0, (max(timestamps) - min(timestamps)) / 1e9)

        ops_per_sec = total_ops / time_span_sec if time_span_sec > 0 else 0.0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        sorted_lat = sorted(latencies)
        p99_idx = max(0, int(len(sorted_lat) * 0.99) - 1)
        p99_latency = sorted_lat[p99_idx] if sorted_lat else 0.0
        cost_estimate = total_ops * 0.001 + avg_latency * 0.0001

        window_data = {
            "window_id": window_id,
            "operations_per_sec": round(ops_per_sec, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "p99_latency_ms": round(p99_latency, 2),
            "total_operations": total_ops,
            "cost_estimate": round(cost_estimate, 6),
        }
        self._windows[window_id] = window_data

        self._publish_event("throughput", window_id, data_trace_id, **window_data)

        return window_data

    def detect_anomalies(  # LAW-5 RULE-3
        self,
        window_id: str,
        metrics: List[Dict[str, Any]],
        baselines: Dict[str, float],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        anomalies: List[Dict[str, Any]] = []
        critical_count = 0

        for metric in metrics:
            m_name = metric.get("metric", metric.get("name", ""))
            m_value = metric.get("value", 0.0)
            if m_name in baselines:
                baseline = baselines[m_name]
                deviation = abs(m_value - baseline) / max(abs(baseline), 0.001) * 100
                if deviation > 10.0:
                    severity = "critical" if deviation > 50.0 else "high" if deviation > 30.0 else "medium"
                    anomalies.append({
                        "metric": m_name,
                        "value": m_value,
                        "baseline": baseline,
                        "deviation_pct": round(deviation, 2),
                        "severity": severity,
                    })
                    if severity == "critical":
                        critical_count += 1

        self._publish_event("anomaly_detection", window_id, data_trace_id,
                            anomaly_count=len(anomalies), critical_count=critical_count)

        return {
            "window_id": window_id,
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "critical_count": critical_count,
        }

    def aggregate_metrics(  # LAW-5 LAW-16 RULE-1
        self,
        window_id: str,
        raw_metrics: List[Dict[str, Any]],
        aggregation_fn: str,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        if not raw_metrics:
            return {"window_id": window_id, "aggregated_value": 0.0,
                    "aggregation_fn": aggregation_fn, "input_count": 0, "output_count": 0}

        values = [m.get("value", 0.0) for m in raw_metrics if "value" in m]
        input_count = len(values)

        if aggregation_fn == "sum":
            result = sum(values)
        elif aggregation_fn == "avg":
            result = sum(values) / len(values) if values else 0.0
        elif aggregation_fn == "min":
            result = min(values) if values else 0.0
        elif aggregation_fn == "max":
            result = max(values) if values else 0.0
        elif aggregation_fn == "count":
            result = float(len(values))
        else:
            result = 0.0

        self._publish_event("aggregate", window_id, data_trace_id,
                            fn=aggregation_fn, result=result, input_count=input_count)

        return {
            "window_id": window_id,
            "aggregated_value": round(result, 4),
            "aggregation_fn": aggregation_fn,
            "input_count": input_count,
            "output_count": 1,
        }

    def publish_dashboard(  # LAW-5
        self,
        dashboard_id: str,
        widgets: List[Dict[str, Any]],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        now_ns = time.time_ns()
        dashboard = {
            "dashboard_id": dashboard_id,
            "widgets": widgets,
            "widget_count": len(widgets),
            "published_at_ns": now_ns,
            "data_trace_id": data_trace_id,
        }
        self._dashboards[dashboard_id] = dashboard

        self._publish_event("dashboard", dashboard_id, data_trace_id, widget_count=len(widgets))

        return {
            "published": True,
            "dashboard_id": dashboard_id,
            "widget_count": len(widgets),
            "published_at_ns": now_ns,
        }
