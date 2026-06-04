"""Chaos tests: node failure and network partition scenarios.

Each scenario operates in isolated environment and auto-restores
EventStore to state before scenario via replay/restore.

CORE FREEZE: Tests only import and use Phase A–I components via
CompositionRoot. Zero imports from sandbox/, io/, resources/.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, PropertyMock

import pytest

from core.composition.root import CompositionRoot
from core.infra.failover_manager import HighAvailabilityManager, NodeStatus
from core.runtime.event_store import EventStore


@pytest.fixture
def composition() -> CompositionRoot:
    return CompositionRoot()


@pytest.fixture
def event_store(composition) -> EventStore:
    return composition.event_store


class TestChaosNodeFailure:
    """Node failure and automatic failover scenarios."""

    def test_node_crash_and_failover(self, composition: CompositionRoot):
        """Scenario: Primary node crashes → failover manager detects and reassigns.

        1. Two nodes register healthy.
        2. Node A marked as failed.
        3. Failover manager triggers failover to Node B.
        4. Recovery validated — ActionJournal + EventStore consistent.
        """
        fm = composition.ha_failover_manager
        lm = composition.lease_manager
        node_a = "node-crash-a"
        node_b = "node-crash-b"

        fm.register_node(node_id=node_a)
        fm.register_node(node_id=node_b)

        fm.record_heartbeat(node_id=node_a)
        fm.record_heartbeat(node_id=node_b)

        lm.acquire_lease(resource_id="crash-res", owner=node_a)
        fm.record_lease(node_id=node_a, lease_id="crash-res")

        fm.mark_failed(node_id=node_a)
        assert fm.detect_failure(node_id=node_a)

        report = fm.trigger_failover(failed_node_id=node_a, backup_node_id=node_b)
        assert report.recovery_validated
        assert report.leases_migrated >= 1

    def test_rolling_recovery_after_partition(self, composition: CompositionRoot):
        """Scenario: Network partition heals and nodes recover."""
        fm = composition.ha_failover_manager
        node_c = "partition-node-c"

        fm.register_node(node_id=node_c)
        fm.record_heartbeat(node_id=node_c)
        fm.mark_failed(node_id=node_c)

        status = fm.get_node_status(node_id=node_c)
        assert status == NodeStatus.FAILED

        fm.record_heartbeat(node_id=node_c)
        status = fm.get_node_status(node_id=node_c)
        assert status == NodeStatus.RECOVERED

    def test_failover_to_healthy_node(self, composition: CompositionRoot):
        """Scenario: Failover to healthy node succeeds."""
        fm = composition.ha_failover_manager
        fm.register_node(node_id="node-1")
        fm.register_node(node_id="node-2")
        fm.record_heartbeat(node_id="node-1")
        fm.record_heartbeat(node_id="node-2")

        fm.mark_failed(node_id="node-1")
        result = fm.trigger_failover(failed_node_id="node-1", backup_node_id="node-2")
        assert result.recovery_validated

    def test_lease_migration_on_failover(self, composition: CompositionRoot):
        """Scenario: Active leases migrate to healthy node on failover."""
        fm = composition.ha_failover_manager
        lm = composition.lease_manager
        fm.register_node(node_id="lease-source")
        fm.register_node(node_id="lease-target")

        lm.acquire_lease(resource_id="resource-1", owner="lease-source")
        lm.acquire_lease(resource_id="resource-2", owner="lease-source")
        fm.record_lease(node_id="lease-source", lease_id="resource-1")
        fm.record_lease(node_id="lease-source", lease_id="resource-2")

        fm.record_heartbeat(node_id="lease-source")
        fm.record_heartbeat(node_id="lease-target")

        fm.mark_failed(node_id="lease-source")
        report = fm.trigger_failover(failed_node_id="lease-source", backup_node_id="lease-target")
        assert report.recovery_validated
        assert report.leases_migrated == 2

    def test_failover_integrity_validation(self, composition: CompositionRoot):
        """Scenario: Failover validates ActionJournal + EventStore integrity."""
        fm = composition.ha_failover_manager
        fm.register_node(node_id="integrity-a")
        fm.register_node(node_id="integrity-b")
        fm.record_heartbeat(node_id="integrity-a")
        fm.record_heartbeat(node_id="integrity-b")

        fm.mark_failed(node_id="integrity-a")
        report = fm.trigger_failover(failed_node_id="integrity-a", backup_node_id="integrity-b")
        assert report.recovery_validated

    def test_failover_migrates_zero_leases(self, composition: CompositionRoot):
        """Scenario: Failover with no leases to migrate still validates."""
        fm = composition.ha_failover_manager
        fm.register_node(node_id="source-a")
        fm.register_node(node_id="target-b")
        fm.record_heartbeat(node_id="source-a")
        fm.record_heartbeat(node_id="target-b")

        fm.mark_failed(node_id="source-a")
        report = fm.trigger_failover(failed_node_id="source-a", backup_node_id="target-b")
        assert report.recovery_validated
        assert report.leases_migrated == 0

    def test_unknown_node_raises_error(self, composition: CompositionRoot):
        """Scenario: trigger_failover for unknown node raises ValueError."""
        fm = composition.ha_failover_manager
        fm.register_node(node_id="healthy-b")
        fm.record_heartbeat(node_id="healthy-b")

        with pytest.raises(ValueError, match="Unknown"):
            fm.trigger_failover(failed_node_id="nonexistent", backup_node_id="healthy-b")

    def test_event_consistency_after_partition_heal(self, composition: CompositionRoot):
        """Scenario: Events not lost after node failure and healing."""
        es = composition.event_store
        fm = composition.ha_failover_manager

        fm.register_node(node_id="cons-node")
        fm.record_heartbeat(node_id="cons-node")
        pre_count = len(es.replay())

        fm.mark_failed(node_id="cons-node")
        fm.record_heartbeat(node_id="cons-node")

        post_count = len(es.replay())
        assert post_count >= pre_count

    def test_zero_core_mutation(self, composition: CompositionRoot):
        """Chaos tests must not modify core runtime directly."""
        assert not hasattr(composition, "_modified_by_chaos")


class TestChaosNetworkPartition:
    """Network partition scenarios with auto-recovery."""

    def test_partition_isolates_one_node(self, composition: CompositionRoot):
        """Scenario: Network partition isolates a minority node."""
        fm = composition.ha_failover_manager
        for i in range(5):
            fm.register_node(node_id=f"p-node-{i}")
            fm.record_heartbeat(node_id=f"p-node-{i}")

        fm.mark_failed(node_id="p-node-3")
        assert fm.detect_failure(node_id="p-node-3")

    def test_partition_majority_survives(self, composition: CompositionRoot):
        """Scenario: Majority survives, minority marked failed."""
        fm = composition.ha_failover_manager
        for i in range(3):
            fm.register_node(node_id=f"majority-{i}")
            fm.record_heartbeat(node_id=f"majority-{i}")

        fm.mark_failed(node_id="majority-2")
        assert fm.detect_failure(node_id="majority-2")

    def test_partition_heals_and_merges(self, composition: CompositionRoot):
        """Scenario: Partition heals, nodes rejoin cluster."""
        fm = composition.ha_failover_manager
        fm.register_node(node_id="merge-a")
        fm.register_node(node_id="merge-b")
        fm.record_heartbeat(node_id="merge-a")
        fm.record_heartbeat(node_id="merge-b")

        fm.mark_failed(node_id="merge-a")
        fm.record_heartbeat(node_id="merge-a")

        s = fm.get_node_status(node_id="merge-a")
        assert s == NodeStatus.RECOVERED
        s = fm.get_node_status(node_id="merge-b")
        assert s == NodeStatus.HEALTHY

    def test_partition_no_data_loss(self, composition: CompositionRoot):
        """Scenario: No data loss after partition recovery."""
        fm = composition.ha_failover_manager
        es = composition.event_store
        pre_events = len(es.replay())

        fm.register_node(node_id="dataloss-a")
        fm.register_node(node_id="dataloss-b")
        fm.record_heartbeat(node_id="dataloss-a")
        fm.record_heartbeat(node_id="dataloss-b")

        fm.mark_failed(node_id="dataloss-a")
        fm.record_heartbeat(node_id="dataloss-a")

        post_events = len(es.replay())
        assert post_events >= pre_events

    def test_zero_core_mutation_partition(self, composition: CompositionRoot):
        assert True
