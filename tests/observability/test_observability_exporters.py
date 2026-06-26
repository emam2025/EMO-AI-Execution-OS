"""Test Prometheus + OpenTelemetry exporters — simple format tests."""

from core.runtime.observability.exporters import PrometheusExporter


class TestPrometheusExporter:
    """Test that PrometheusExporter generates correct metrics format."""

    def test_generate_metrics_returns_bytes(self):
        exporter = PrometheusExporter()
        result = exporter.generate_metrics()
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_record_request_appears_in_metrics(self):
        exporter = PrometheusExporter()
        exporter.record_request("GET", "/api/agents", 200, 0.05)
        metrics = exporter.generate_metrics().decode("utf-8")
        assert "emo_requests_total" in metrics
        assert 'method="GET"' in metrics
        assert 'endpoint="/api/agents"' in metrics
        assert 'status="200"' in metrics

    def test_record_audit_event_appears(self):
        exporter = PrometheusExporter()
        exporter.record_audit_event("workflow.execute", "success")
        metrics = exporter.generate_metrics().decode("utf-8")
        assert "emo_audit_events_total" in metrics
        assert 'action="workflow.execute"' in metrics

    def test_set_active_agents(self):
        exporter = PrometheusExporter()
        exporter.set_active_agents(5)
        metrics = exporter.generate_metrics().decode("utf-8")
        assert "emo_active_agents" in metrics
        assert "5" in metrics

    def test_set_memory_entries_by_layer(self):
        exporter = PrometheusExporter()
        exporter.set_memory_entries("PROJECT", 42)
        metrics = exporter.generate_metrics().decode("utf-8")
        assert "emo_memory_entries" in metrics
        assert 'layer="PROJECT"' in metrics

    def test_content_type_is_string(self):
        exporter = PrometheusExporter()
        assert isinstance(exporter.CONTENT_TYPE, str)
        assert "text/plain" in exporter.CONTENT_TYPE
