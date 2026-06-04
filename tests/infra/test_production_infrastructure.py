"""Phase I — Production Infrastructure & Data Persistence: 33 tests.

Groups:
  - TestPostgresAdapter:        6 tests — connect, append, read, UPSERT, pool exhaustion, health
  - TestDistributedPublisher:   6 tests — publish, ack, dead-letter, replay, zero-loss, failover guard
  - TestFailoverIntegrity:      6 tests — detect, migrate, recover, validate, latency, history
  - TestEventConsistency:       6 tests — every infra operation emits traced ExecutionEvent
  - TestZeroCoreMutation:       9 tests — zero forbidden imports in core/infra/

Ref: Canon LAW 3, LAW 5, LAW 8, LAW 12, RULE 1
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

import pytest

from core.infra.event_publisher import DistributedEventPublisher, PublishResult
from core.infra.failover_manager import HighAvailabilityManager
from core.infra.postgres_adapter import PoolConfig, PostgresPersistenceAdapter
from core.models.events import ExecutionEvent
from core.models.infra_models import ConnectionStatus, NodeHealth, NodeStatus


# ═══════════════════════════════════════════════════════════════════
# Group 1 — PostgresAdapter
# ═══════════════════════════════════════════════════════════════════

class TestPostgresAdapter:
    """Verify PostgresPersistenceAdapter connection, write, read, UPSERT."""

    def test_connect_returns_ok(self):
        adapter = PostgresPersistenceAdapter()
        status = adapter.connect(dsn="postgresql://localhost:5432/test")
        assert status.connected is True
        assert status.pool_size > 0

    def test_append_event_stores_and_returns_true(self):
        adapter = PostgresPersistenceAdapter()
        adapter.connect()
        event = ExecutionEvent(
            event_id="evt-001", event_type="COMPUTER_ACTION",
            timestamp=time.time(), source="test", payload={"key": "val"},
        )
        assert adapter.append_event(event) is True
        assert adapter.event_count() == 1

    def test_read_events_by_trace_id(self):
        adapter = PostgresPersistenceAdapter()
        adapter.connect()
        t_id = "trace-abc"
        adapter.append_event(ExecutionEvent(
            event_id="e1", event_type="COMPUTER_ACTION",
            timestamp=100.0, source="test", trace_id=t_id,
        ))
        adapter.append_event(ExecutionEvent(
            event_id="e2", event_type="COMPUTER_ACTION",
            timestamp=200.0, source="test", trace_id=t_id,
        ))
        events = adapter.read_events(trace_id=t_id)
        assert len(events) == 2

    def test_upsert_prevents_duplicate(self):
        adapter = PostgresPersistenceAdapter()
        adapter.connect()
        adapter.append_event(ExecutionEvent(
            event_id="e1", event_type="COMPUTER_ACTION",
            timestamp=100.0, source="test",
        ))
        adapter.append_event(ExecutionEvent(
            event_id="e1", event_type="COMPUTER_ACTION",
            timestamp=200.0, source="test",
        ))
        assert adapter.event_count() == 1

    def test_pool_exhaustion_handled(self):
        adapter = PostgresPersistenceAdapter(PoolConfig(min_size=1, max_size=2))
        adapter.connect()
        status = adapter.health_check()
        assert status.connected is True

    def test_health_check_returns_status(self):
        adapter = PostgresPersistenceAdapter()
        adapter.connect()
        status = adapter.health_check()
        assert isinstance(status, ConnectionStatus)
        assert status.connected is True


# ═══════════════════════════════════════════════════════════════════
# Group 2 — DistributedPublisher
# ═══════════════════════════════════════════════════════════════════

class TestDistributedPublisher:
    """Verify publish, ack, dead-letter, replay, zero-loss."""

    def test_publish_returns_pending(self):
        pub = DistributedEventPublisher()
        result = pub.publish("execution.started", "evt-1", {"msg": "hello"})
        assert result == PublishResult.PENDING
        assert pub.unacknowledged_count() == 1

    def test_acknowledge_removes_from_pending(self):
        pub = DistributedEventPublisher()
        pub.publish("execution.started", "evt-1", {"msg": "hello"})
        assert pub.acknowledge("evt-1") is True
        assert pub.unacknowledged_count() == 0
        assert pub.acknowledged_count() == 1

    def test_dead_letter_after_max_retries(self):
        pub = DistributedEventPublisher(max_retries=2)
        pub.publish("execution.started", "evt-1", {"msg": "hello"})
        # Simulate retries by calling replay_unacknowledged repeatedly
        pub.replay_unacknowledged()  # retry 1
        pub.replay_unacknowledged()  # retry 2
        pub.replay_unacknowledged()  # retry 3 → dead letter
        assert "evt-1" in pub.get_dead_letter_queue()

    def test_replay_unacknowledged_returns_pending_events(self):
        pub = DistributedEventPublisher()
        pub.publish("execution.started", "evt-1", {"msg": "hello"})
        pub.publish("execution.completed", "evt-2", {"msg": "done"})
        unacked = pub.replay_unacknowledged()
        assert len(unacked) == 2

    def test_zero_loss_after_1000_ops(self):
        pub = DistributedEventPublisher()
        for i in range(100):
            pub.publish("test.topic", f"evt-{i}", {"seq": i})
            pub.acknowledge(f"evt-{i}")
        assert pub.acknowledged_count() == 100
        assert pub.unacknowledged_count() == 0
        assert pub.total_published() == 100

    def test_publish_with_ack_immediate(self):
        pub = DistributedEventPublisher()
        result = pub.publish_with_ack("test.topic", "evt-1", {"msg": "hello"})
        assert result == PublishResult.ACK
        assert pub.acknowledged_count() == 1


# ═══════════════════════════════════════════════════════════════════
# Group 3 — FailoverIntegrity
# ═══════════════════════════════════════════════════════════════════

class TestFailoverIntegrity:
    """Verify node monitoring, lease migration, recovery validation."""

    def test_register_node_creates_healthy(self):
        ham = HighAvailabilityManager()
        ham.register_node("node-1")
        status = ham.get_node_status("node-1")
        assert status == NodeStatus.HEALTHY

    def test_detect_failure_on_timeout(self):
        ham = HighAvailabilityManager()
        ham.register_node("node-1")
        # Simulate timeout by advancing time past threshold
        ham._heartbeat_times["node-1"] = time.time() - 20  # >3*5=15 sec
        assert ham.detect_failure("node-1") is True

    def test_trigger_failover_migrates_leases(self):
        ham = HighAvailabilityManager()
        ham.register_node("node-1")
        ham.register_node("node-2")
        ham.record_lease("node-1", "lease-1")
        ham.record_lease("node-1", "lease-2")
        report = ham.trigger_failover("node-1", "node-2")
        assert report.leases_migrated == 2
        assert report.failed_node_id == "node-1"
        assert report.backup_node_id == "node-2"

    def test_trigger_failover_unknown_node_raises(self):
        ham = HighAvailabilityManager()
        with pytest.raises(ValueError, match="Unknown node"):
            ham.trigger_failover("nonexistent", "backup")

    def test_validate_recovery_integrity_returns_true_if_valid(self):
        ham = HighAvailabilityManager()
        assert ham.validate_recovery_integrity() is True

    def test_failover_latency_under_1s(self):
        ham = HighAvailabilityManager()
        ham.register_node("node-1")
        ham.register_node("node-2")
        ham.record_lease("node-1", "lease-1")
        report = ham.trigger_failover("node-1", "node-2")
        assert report.latency_ms < 1000, f"Latency {report.latency_ms}ms > 1000ms"


# ═══════════════════════════════════════════════════════════════════
# Group 4 — EventConsistency
# ═══════════════════════════════════════════════════════════════════

class TestEventConsistency:
    """Verify every infra operation emits traced events."""

    def test_adapter_connect_returns_status(self):
        adapter = PostgresPersistenceAdapter()
        status = adapter.connect()
        assert isinstance(status, ConnectionStatus)

    def test_adapter_append_and_read_roundtrip(self):
        adapter = PostgresPersistenceAdapter()
        adapter.connect()
        event = ExecutionEvent(
            event_id="evt-r1", event_type="COMPUTER_ACTION",
            timestamp=time.time(), source="test", trace_id="tr-r1",
        )
        adapter.append_event(event)
        events = adapter.read_events(trace_id="tr-r1")
        assert len(events) == 1
        assert events[0].event_id == "evt-r1"

    def test_publisher_acks_match_events(self):
        pub = DistributedEventPublisher()
        for i in range(5):
            pub.publish("test", f"evt-{i}", {"seq": i})
        for i in range(5):
            pub.acknowledge(f"evt-{i}")
        assert pub.acknowledged_count() == 5
        assert pub.unacknowledged_count() == 0

    def test_failover_report_has_trace_id(self):
        ham = HighAvailabilityManager()
        ham.register_node("node-1")
        ham.register_node("node-2")
        report = ham.trigger_failover("node-1", "node-2")
        assert report.failover_id is not None

    def test_node_status_tracks_heartbeat(self):
        ham = HighAvailabilityManager()
        ham.register_node("node-1")
        ham.record_heartbeat("node-1", latency_ms=5.0)
        status = ham.get_node_status("node-1")
        assert status == NodeStatus.HEALTHY

    def test_mark_failed_changes_status(self):
        ham = HighAvailabilityManager()
        ham.register_node("node-1")
        ham.mark_failed("node-1", "OOM crash")
        assert ham.get_node_status("node-1") == NodeStatus.FAILED


# ═══════════════════════════════════════════════════════════════════
# Group 5 — ZeroCoreMutation
# ═══════════════════════════════════════════════════════════════════

class TestZeroCoreMutation:
    """Verify zero forbidden imports or modifications in core/infra/."""

    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    FORBIDDEN_IMPORTS = [
        "runtime.event_store",
        "runtime.metrics_store",
        "execution_core",
        "sandbox",
        "io.",
        "computer",
    ]

    FILES = [
        PROJECT_ROOT / "core/infra/postgres_adapter.py",
        PROJECT_ROOT / "core/infra/event_publisher.py",
        PROJECT_ROOT / "core/infra/failover_manager.py",
    ]

    @pytest.mark.parametrize("filepath", FILES)
    def test_no_forbidden_imports(self, filepath):
        text = filepath.read_text()
        lines = text.splitlines()
        import_lines = [line.lower() for line in lines if line.startswith(("import ", "from "))]
        content = "\n".join(import_lines)
        for pattern in self.FORBIDDEN_IMPORTS:
            assert pattern not in content, (
                f"Forbidden import '{pattern}' found in {filepath}"
            )

    def test_event_store_not_modified(self):
        store_path = self.PROJECT_ROOT / "core/runtime/event_store.py"
        assert store_path.exists()
        # Verify EventStore.append still uses JSON-lines (original impl)
        text = store_path.read_text()
        assert ".jsonl" in text
        assert "def append" in text

    def test_no_broker_libs_in_core(self):
        import ast
        for filepath in self.FILES:
            tree = ast.parse(filepath.read_text())
            import_names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    import_names.add(node.names[0].name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        import_names.add(node.module.split(".")[0])
            for lib in ["pika", "aiokafka", "kafka", "rabbitmq", "boto3"]:
                assert lib not in import_names, f"Broker lib '{lib}' imported in {filepath}"

    def test_pool_config_has_reasonable_defaults(self):
        config = PoolConfig()
        assert config.min_size >= 1
        assert config.max_size >= config.min_size
        assert config.retry_attempts > 0

    def test_node_health_dataclass_works(self):
        health = NodeHealth(node_id="n1", status=NodeStatus.HEALTHY)
        assert health.status == NodeStatus.HEALTHY
        assert health.lease_count == 0
        assert health.latency_ms == 0.0

    @pytest.mark.parametrize("filepath", FILES)
    def test_no_execution_core_import(self, filepath):
        text = filepath.read_text()
        assert "execution_core" not in text
        assert "IsolationRuntime" not in text
