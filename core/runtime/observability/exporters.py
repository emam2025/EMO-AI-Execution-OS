"""Observability exporters — Prometheus metrics + OpenTelemetry traces.

Prometheus: /metrics endpoint for scraping by Prometheus server.
  Subscribes to TelemetryAggregator events (future — currently manual recording).

OpenTelemetry: trace export to OTLP-compatible backend (Jaeger, Tempo, etc.).
  Manual span creation (no auto-instrumentation — lighter).

Environment variables:
    OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (e.g., http://localhost:4317)
    OTEL_SERVICE_NAME: Service name (default: emo-ai)
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("emo_ai.observability.exporters")


class PrometheusExporter:
    """Prometheus metrics exporter.

    Records counters, histograms, and gauges.
    Designed to feed from the same sources as TelemetryAggregator.
    """

    def __init__(self, telemetry_aggregator=None):
        from prometheus_client import (
            CollectorRegistry,
            Counter,
            Histogram,
            Gauge,
            generate_latest,
            CONTENT_TYPE_LATEST,
        )

        self._registry = CollectorRegistry()
        self._generate_latest = generate_latest
        self.CONTENT_TYPE = CONTENT_TYPE_LATEST

        # HTTP metrics
        self._requests = Counter(
            "emo_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
            registry=self._registry,
        )
        self._latency = Histogram(
            "emo_request_duration_seconds",
            "Request latency in seconds",
            ["endpoint"],
            registry=self._registry,
        )

        # Runtime metrics
        self._active_agents = Gauge(
            "emo_active_agents",
            "Number of active agents",
            registry=self._registry,
        )
        self._memory_entries = Gauge(
            "emo_memory_entries",
            "Memory entries by layer",
            ["layer"],
            registry=self._registry,
        )

        # Governance metrics
        self._audit_events = Counter(
            "emo_audit_events_total",
            "Total audit events recorded",
            ["action", "outcome"],
            registry=self._registry,
        )
        self._approvals_pending = Gauge(
            "emo_approvals_pending",
            "Pending approval requests",
            registry=self._registry,
        )

        # Scheduler metrics
        self._scheduled_tasks = Counter(
            "emo_scheduled_tasks_total",
            "Total scheduled tasks",
            ["status"],
            registry=self._registry,
        )
        self._active_workers = Gauge(
            "emo_active_workers",
            "Active worker count",
            registry=self._registry,
        )

        if telemetry_aggregator:
            self._subscribe_to_telemetry(telemetry_aggregator)

    def _subscribe_to_telemetry(self, telemetry_aggregator) -> None:
        """Subscribe to TelemetryAggregator events.

        Future: wire to EventBus subscription when TelemetryAggregator
        publishes regular summaries.  For now, recording is manual.
        """
        logger.info("PrometheusExporter attached (subscription: future)")

    def record_request(
        self, method: str, endpoint: str, status: int, duration: float
    ) -> None:
        self._requests.labels(
            method=method, endpoint=endpoint, status=str(status)
        ).inc()
        self._latency.labels(endpoint=endpoint).observe(duration)

    def set_active_agents(self, count: int) -> None:
        self._active_agents.set(count)

    def set_memory_entries(self, layer: str, count: int) -> None:
        self._memory_entries.labels(layer=layer).set(count)

    def record_audit_event(self, action: str, outcome: str) -> None:
        self._audit_events.labels(action=action, outcome=outcome).inc()

    def set_pending_approvals(self, count: int) -> None:
        self._approvals_pending.set(count)

    def record_scheduled_task(self, status: str) -> None:
        self._scheduled_tasks.labels(status=status).inc()

    def set_active_workers(self, count: int) -> None:
        self._active_workers.set(count)

    def generate_metrics(self) -> bytes:
        """Generate Prometheus-format metrics for /metrics endpoint."""
        return self._generate_latest(registry=self._registry)


class OpenTelemetryExporter:
    """OpenTelemetry trace exporter.

    Only active if OTEL_EXPORTER_OTLP_ENDPOINT is set.
    Manual span creation (no auto-instrumentation).
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        service_name: str = "emo-ai",
    ):
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        if endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OpenTelemetry traces exporting to %s", endpoint)

        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(__name__)

    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Start a new OpenTelemetry span manually."""
        span = self._tracer.start_span(name)
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, str(v))
        return span
